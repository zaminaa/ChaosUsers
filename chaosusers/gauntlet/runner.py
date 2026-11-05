import hashlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from chaosusers import __version__
from chaosusers.config import RunConfig, build_client, resolve_models
from chaosusers.engine.persona import build_instance
from chaosusers.engine.prompts import prompt_hashes
from chaosusers.gauntlet.driver import run_conversation
from chaosusers.gauntlet.judge import judge_transcript, load_rubric
from chaosusers.gauntlet.scenario import load_scenario
from chaosusers.gauntlet.score import aggregate, load_grade_rubric, score_conversation
from chaosusers.gauntlet.targets import load_target
from chaosusers.llm.budget import Pricing
from chaosusers.llm.client import LLMOutputError
from chaosusers.packs.loader import load_pack, load_taxonomy
from chaosusers.record.predictions import canonical_sha256, predictions_from_gauntlet
from chaosusers.record.recorder import RunRecorder
from chaosusers.record.schema import Manifest

_LABELS = {
    "success": ("✓", "done"),
    "silent_failure": ("✗", "TOLD DONE — NOT DONE"),
    "forbidden_action": ("✗", "FORBIDDEN ACTION"),
    "stuck": ("✗", "stuck (turn cap)"),
    "incomplete": ("✗", "incomplete"),
    "unverified": ("✗", "unverified"),
    "error": ("!", "error"),
}
_ABANDON = {"leave": "gave up", "block": "blocked the bot", "go_silent": "went silent", "demand_human": "asked for a human"}


def plan_gauntlet(cfg: RunConfig) -> dict:
    personas = _select(cfg)
    conversations = len(personas) * cfg.repeats
    price = Pricing.load().price(cfg.model or Pricing.load().default_model("openai"))
    pin, pout = price or (0.0, 0.0)
    persona_cost = (2500 * pin + 300 * pout) / 1_000_000
    judge_cost = (3500 * pin + 900 * pout) / 1_000_000
    worst = conversations * cfg.max_turns * persona_cost + conversations * cfg.judge_samples * judge_cost
    return {
        "personas": [persona.id for persona in personas],
        "conversations": conversations,
        "max_llm_calls": conversations * (cfg.max_turns + 1) + conversations * cfg.judge_samples * 2,
        "worst_case_usd": worst,
        "worst_case_tokens": conversations * cfg.max_turns * (2500 + 300) + conversations * cfg.judge_samples * (3500 + 900),
    }


def run_gauntlet(cfg: RunConfig, progress=print) -> Path:
    cfg = resolve_models(cfg) if cfg.provider or cfg.model else cfg
    pack = load_pack(cfg.pack)
    scenario = load_scenario(cfg.scenario or "demo")
    target = load_target(cfg.target or "demo")
    personas = _select(cfg, pack)
    rubric, rubric_sha = load_rubric("gauntlet_v1")
    grade_rubric = load_grade_rubric()
    planned = plan_gauntlet(cfg)
    progress(f"Worst-case cost: ${planned['worst_case_usd']:.2f} (cap ${cfg.max_usd:.2f})")
    if planned["worst_case_usd"] > cfg.max_usd:
        progress("Worst case exceeds the cap. The run will stop cleanly at the cap.")
    recorder = RunRecorder(cfg.out_dir, "gauntlet")
    client, budget = build_client(cfg, recorder.call_log_path())
    _price_script(cfg, budget)
    model = cfg.model or Pricing.load().default_model(cfg.provider or "openai")
    judge_model = cfg.judge_model or model
    stop = threading.Event()
    scored = []
    lock = threading.Lock()

    def unit(job: tuple) -> None:
        persona, repeat = job
        if stop.is_set():
            return
        seed = _conv_seed(cfg.seed, persona.id, repeat)
        instance = build_instance(persona, seed, scenario)
        transcript = run_conversation(
            instance, scenario, target, client, pack, model,
            min(cfg.max_turns, scenario.max_turns or cfg.max_turns), repeat, recorder.run_id,
        )
        if transcript.end_reason == "budget_exhausted":
            stop.set()
        judge, ungrounded = {}, 0
        if transcript.end_reason not in {"budget_exhausted", "target_error"} and transcript.turns:
            try:
                judge, ungrounded = judge_transcript(transcript, rubric, client, judge_model, cfg.judge_samples, seed + 1000)
            except LLMOutputError:
                ungrounded = cfg.judge_samples
        if stop.is_set() and transcript.end_reason == "budget_exhausted" and not transcript.turns:
            return
        item = score_conversation(transcript, scenario, judge, ungrounded, pack)
        with lock:
            scored.append(item)
        recorder.append_jsonl("transcripts.jsonl", transcript)
        progress(_line(item, pack))

    jobs = [(persona, repeat) for persona in personas for repeat in range(cfg.repeats)]
    workers = max(1, cfg.concurrency)
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(unit, jobs))
    status = "complete"
    if any(item.outcome == "error" for item in scored) or stop.is_set():
        status = "budget_exhausted" if stop.is_set() else "partial_error"
    if any(item.outcome == "error" for item in scored) and not stop.is_set():
        status = "partial_error"
    if stop.is_set():
        status = "budget_exhausted"
    scores = aggregate(scored, pack, rubric, cfg.repeats, status)
    taxonomy = load_taxonomy()
    predicted = predictions_from_gauntlet(scores, scenario, pack, taxonomy, recorder.run_id, target.name)
    receipt = canonical_sha256(predicted)
    manifest = Manifest(
        run_id=recorder.run_id,
        created_at=datetime.now(UTC).isoformat(),
        chaosusers_version=__version__,
        mode="gauntlet",
        command=sys.argv,
        status=status,
        replay_of=str(cfg.replay) if cfg.replay else None,
        scripted=cfg.script is not None,
        provider=cfg.provider or ("script" if cfg.script else "replay" if cfg.replay else "openai"),
        persona_model=model,
        judge_model=judge_model,
        settings={
            "repeats": cfg.repeats, "judge_samples": cfg.judge_samples, "max_turns": cfg.max_turns,
            "max_usd": cfg.max_usd, "max_tokens": cfg.max_tokens, "seed": cfg.seed, "concurrency": cfg.concurrency,
        },
        pack={"id": pack.meta.id, "version": pack.meta.version, "sha256": pack.sha256},
        personas=[persona.id for persona in personas],
        scenario={"id": scenario.id, "version": scenario.version, "sha256": scenario.sha256},
        target=target.describe(),
        prompts=prompt_hashes(),
        rubric={"id": rubric.id, "version": rubric.version, "sha256": rubric_sha, "grade": grade_rubric["id"]},
        cost={
            "usd": budget.spent_usd, "tokens_in": budget.spent_in, "tokens_out": budget.spent_out,
            "llm_calls": budget.calls, "target_calls": sum(item.user_turns for item in scored),
            "worst_case_usd": planned["worst_case_usd"],
        },
        predictions_sha256=receipt,
    )
    recorder.write_json("scores.json", scores)
    recorder.write_json("predictions.json", predicted)
    recorder.write_json("manifest.json", manifest)
    _try_render(recorder.path)
    progress(f"Grade: {scores.grade or 'UNGRADED'}")
    progress(f"Prediction receipt: sha256:{receipt}")
    progress(f"Report: {recorder.path / 'report.html'}")
    return recorder.path


def _price_script(cfg: RunConfig, budget) -> None:
    if cfg.script is None:
        return
    pair = Pricing.load().price(cfg.model or Pricing.load().default_model("openai"))
    if pair:
        budget.price_in, budget.price_out = pair


def _select(cfg: RunConfig, pack=None):
    pack = pack or load_pack(cfg.pack)
    chosen = pack.for_mode("gauntlet")
    if cfg.personas:
        wanted = set(cfg.personas)
        chosen = [persona for persona in chosen if persona.id in wanted]
    return chosen


def _conv_seed(run_seed: int, persona_id: str, repeat: int) -> int:
    return int(hashlib.sha256(f"{run_seed}:{persona_id}:{repeat}".encode()).hexdigest()[:8], 16)


def _line(item, pack) -> str:
    persona = pack.personas[item.persona_id]
    if item.outcome == "abandoned":
        symbol, label = "✗", _ABANDON.get(item.abandon_action or "leave", "gave up")
    else:
        symbol, label = _LABELS[item.outcome]
    tail = f"@ {item.failure_step}" if item.failure_step else ""
    return f"{persona.name:<7}{persona.archetype:<30}{symbol} {label:<26}{tail}"


def _try_render(path) -> None:
    try:
        from chaosusers.report.render import write_reports
    except ImportError:
        return
    write_reports(path)
