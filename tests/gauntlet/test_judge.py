import json

from chaosusers.engine.prompts import render
from chaosusers.gauntlet.driver import Transcript, Turn
from chaosusers.gauntlet.judge import judge_transcript, load_rubric, normalize
from chaosusers.llm.budget import Budget
from chaosusers.llm.client import LLMClient
from chaosusers.llm.testing import ScriptedProvider


def _client(lines: list[str]) -> LLMClient:
    return LLMClient(ScriptedProvider({"default": lines}), Budget(1, 100_000, 0, 0), None)


def _payload(label: str, quote: str, turn: int = 2) -> str:
    rubric, _sha = load_rubric("gauntlet_v1")
    proven = "Done! Your delivery address has been updated."
    body = {}
    for dim in rubric.dimensions:
        if dim.id == "task_completed":
            body[dim.id] = {"label": label, "evidence": [{"turn": turn, "quote": quote}] if quote else [], "rationale": "because"}
            continue
        chosen = next((item for item in dim.labels if item.no_evidence), dim.labels[0])
        evidence = [] if chosen.no_evidence else [{"turn": 2, "quote": proven}]
        body[dim.id] = {"label": chosen.id, "evidence": evidence, "rationale": "ok"}
    return json.dumps(body)


def _transcript() -> Transcript:
    return Transcript(
        conversation_id="tess--r0",
        persona_id="three-word-answerer",
        scenario_id="s",
        repeat=0,
        seed=1,
        remembered_facts={},
        turns=[Turn(index=1, role="user", text="yes please"), Turn(index=2, role="bot", text="Done! Your delivery address has been updated.")],
        end_reason="persona_done",
    )


def test_quote_must_be_in_the_turn():
    rubric, _sha = load_rubric("gauntlet_v1")
    consensus, ungrounded = judge_transcript(_transcript(), rubric, _client([_payload("yes", "not in the transcript")]), "m", 1, 1)
    assert consensus["task_completed"].n_valid == 0
    assert ungrounded == 1


def test_whitespace_and_case_are_accepted():
    rubric, _sha = load_rubric("gauntlet_v1")
    consensus, ungrounded = judge_transcript(
        _transcript(), rubric, _client([_payload("yes", "  DONE! your   delivery address has been updated. ")]), "m", 1, 1,
    )
    assert consensus["task_completed"].label == "yes"
    assert ungrounded == 0


def test_no_evidence_label_can_be_empty():
    rubric, _sha = load_rubric("gauntlet_v1")
    raw = json.loads(_payload("unclear", ""))
    raw["task_completed"]["label"] = "unclear"
    raw["task_completed"]["evidence"] = []
    consensus, ungrounded = judge_transcript(_transcript(), rubric, _client([json.dumps(raw)]), "m", 1, 1)
    assert consensus["task_completed"].label == "unclear"
    assert ungrounded == 0


def test_majority_and_split():
    rubric, _sha = load_rubric("gauntlet_v1")
    quote = "Done! Your delivery address has been updated."
    yes_line = _payload("yes", quote)
    no_line = _payload("no", quote)
    prefix = "judge:three-word-answerer:r0:"
    yes = judge_transcript(
        _transcript(),
        rubric,
        LLMClient(ScriptedProvider({prefix + "s0": [yes_line], prefix + "s1": [yes_line], prefix + "s2": [no_line]}), Budget(1, 100_000, 0, 0), None),
        "m",
        3,
        1,
    )[0]
    assert yes["task_completed"].label == "yes"
    assert yes["task_completed"].labels == ["yes", "yes", "no"]
    assert round(yes["task_completed"].agreement, 2) == 0.67
    split = judge_transcript(
        _transcript(),
        rubric,
        LLMClient(
            ScriptedProvider({prefix + "s0": [yes_line], prefix + "s1": [no_line], prefix + "s2": [_payload("unclear", "")]}),
            Budget(1, 100_000, 0, 0),
            None,
        ),
        "m",
        3,
        2,
    )[0]
    assert split["task_completed"].label == "uncertain"


def test_invalid_label_drops_the_sample():
    rubric, _sha = load_rubric("gauntlet_v1")
    raw = json.loads(_payload("yes", "Done! Your delivery address has been updated."))
    raw["task_completed"]["label"] = "maybe"
    consensus, ungrounded = judge_transcript(_transcript(), rubric, _client([json.dumps(raw)]), "m", 1, 1)
    assert consensus["task_completed"].n_valid == 0
    assert ungrounded == 1


def test_judge_prompt_is_blind():
    rubric, _sha = load_rubric("gauntlet_v1")
    system, user = render("judge_gauntlet_v1", rubric=rubric, turns=_transcript().turns)
    rendered = f"{system}\n{user}".lower()
    assert "tess" not in rendered
    assert "three-word" not in rendered
    assert "bc03" not in rendered
    assert normalize("  Yes   Please ") == "yes please"
