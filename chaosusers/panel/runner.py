import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from chaosusers import __version__
from chaosusers.config import RunConfig, build_client
from chaosusers.engine.persona import language_examples, language_instruction
from chaosusers.engine.prompts import prompt_hashes, render
from chaosusers.llm.budget import Pricing
from chaosusers.llm.client import LLMOutputError
from chaosusers.llm.types import LLMRequest, Message
from chaosusers.packs.loader import load_pack
from chaosusers.panel.aggregate import aggregate_panel
from chaosusers.panel.artifact import load_artifact, visible_text
from chaosusers.panel.grounding import ground_findings
from chaosusers.panel.models import PanelOutput, PanelResponse
from chaosusers.record.predictions import canonical_sha256, predictions_from_panel
from chaosusers.record.recorder import RunRecorder
from chaosusers.record.schema import Manifest


def plan_panel(cfg: RunConfig) -> dict:
    pack = load_pack(cfg.pack)
    personas = _select(cfg, pack)
    artifact = load_artifact(cfg.artifact or "examples/artifacts/acme-landing.html", cfg.artifact_kind)
    conversations = len(personas) * cfg.repeats
    price = Pricing.load().price(cfg.model or Pricing.load().default_model("openai"))
    pin, pout = price or (0.0, 0.0)
    worst = conversations * (2500 * pin + 1500 * pout) / 1_000_000
    return {
        "personas": [persona.id for persona in personas],
        "sections": len(artifact.sections),
        "conversations": conversations,
        "max_llm_calls": conversations * 2,
        "worst_case_usd": worst,
        "worst_case_tokens": conversations * (2500 + 1500),
    }


def run_panel(cfg: RunConfig, progress=print) -> Path:
    pack = load_pack(cfg.pack)
    artifact = load_artifact(cfg.artifact or "", cfg.artifact_kind)
    personas = _select(cfg, pack)
    planned = plan_panel(cfg)
    progress(f"Worst-case cost: ${planned['worst_case_usd']:.2f} (cap ${cfg.max_usd:.2f})")
    progress(f"Sections: {planned['sections']}")
    recorder = RunRecorder(cfg.out_dir, "panel")
    client, budget = build_client(cfg, recorder.call_log_path())
    if cfg.script is not None:
        pair = Pricing.load().price(cfg.model or Pricing.load().default_model("openai"))
        if pair:
            budget.price_in, budget.price_out = pair
    model = cfg.model or Pricing.load().default_model(cfg.provider or "openai")
    responses = []
    lock = threading.Lock()

    def unit(job: tuple) -> None:
        persona, repeat = job
        visible = {section.id: visible_text(section, persona.panel.reading) for section in artifact.sections if persona.panel}
        words = sum(len(text.split()) for text in visible.values())
        system, user = render(
            "persona_panel_v1",
            p=persona,
            kind_label=artifact.kind,
            language_instruction=language_instruction(pack, persona.language),
            language_examples=language_examples(pack, persona.language),
            sections=[{"id": section.id, "title": section.title, "visible": visible[section.id]} for section in artifact.sections],
        )
        request = LLMRequest(
            purpose="panel", tag=f"panel:{persona.id}:r{repeat}", model=model,
            messages=[Message(role="system", content=system), Message(role="user", content=user)],
            temperature=0.8, max_tokens=1500, seed=cfg.seed + repeat,
        )
        output = None
        error = None
        try:
            output = client.complete_json(request, PanelOutput.model_validate)
        except LLMOutputError as exc:
            error = str(exc)
        response = PanelResponse(persona_id=persona.id, repeat=repeat, output=output, valid=output is not None, error=error, words_read=words)
        ground_findings(response, artifact, visible)
        with lock:
            responses.append(response)
        grounded = 0
        if response.output:
            grounded = sum(finding.grounded for finding in response.output.findings)
        label = response.output.verdict if response.output else "invalid"
        progress(f"{persona.name:<7}{persona.archetype:<30}{label:<18}{grounded} findings ({grounded} grounded)")
        recorder.append_jsonl("panel_responses.jsonl", response)

    jobs = [(persona, repeat) for persona in personas for repeat in range(cfg.repeats)]
    with ThreadPoolExecutor(max(1, cfg.concurrency)) as pool:
        list(pool.map(unit, jobs))
    scores = aggregate_panel(responses, artifact, cfg.repeats, "complete")
    predicted = predictions_from_panel(scores, artifact, pack, recorder.run_id)
    receipt = canonical_sha256(predicted)
    manifest = Manifest(
        run_id=recorder.run_id, created_at=datetime.now(UTC).isoformat(), chaosusers_version=__version__,
        mode="panel", command=sys.argv, status="complete", scripted=cfg.script is not None,
        provider=cfg.provider or ("script" if cfg.script else "openai"), persona_model=model, judge_model=None,
        settings={"repeats": cfg.repeats, "max_usd": cfg.max_usd, "seed": cfg.seed},
        pack={"id": pack.meta.id, "version": pack.meta.version, "sha256": pack.sha256},
        personas=[persona.id for persona in personas],
        artifact={"source": artifact.source, "kind": artifact.kind, "sha256": artifact.sha256, "total_words": artifact.total_words, "truncated": artifact.truncated},
        prompts=prompt_hashes(),
        cost={"usd": budget.spent_usd, "tokens_in": budget.spent_tokens, "tokens_out": 0, "llm_calls": budget.calls, "target_calls": 0, "worst_case_usd": planned["worst_case_usd"]},
        predictions_sha256=receipt,
    )
    recorder.write_json("artifact.json", artifact)
    recorder.write_json("scores.json", scores)
    recorder.write_json("predictions.json", predicted)
    recorder.write_json("manifest.json", manifest)
    try:
        from chaosusers.report.render import write_reports
        write_reports(recorder.path)
    except ImportError:
        pass
    would_not = sum(verdict != "would_complete" for verdict in scores["verdicts"].values())
    biggest = scores["friction"][0] if scores["friction"] else None
    if biggest:
        progress(f"{would_not} of {len(personas)} personas would not complete. Biggest friction: {biggest['section_id']} '{biggest['title']}' — {len(biggest['personas'])} personas.")
    progress(f"Prediction receipt: sha256:{receipt}")
    return recorder.path


def _select(cfg: RunConfig, pack):
    chosen = pack.for_mode("panel")
    if cfg.personas:
        wanted = set(cfg.personas)
        chosen = [persona for persona in chosen if persona.id in wanted]
    return chosen
