from chaosusers.gauntlet.driver import Transcript, Turn
from chaosusers.gauntlet.judge import DimConsensus, load_rubric
from chaosusers.gauntlet.scenario import load_scenario
from chaosusers.gauntlet.score import (
    ConversationScore,
    aggregate,
    compute_grade,
    load_grade_rubric,
    score_conversation,
)
from chaosusers.packs.loader import load_pack


def _judge(label: str, agreement: float = 1.0, n_valid: int = 3) -> dict[str, DimConsensus]:
    return {"task_completed": DimConsensus(label=label, agreement=agreement, n_valid=n_valid, labels=[label])}


def _conv(persona: str, repeat: int, outcome: str, step: str | None = "confirm_address") -> ConversationScore:
    return ConversationScore(
        conversation_id=f"{persona}--r{repeat}", persona_id=persona, repeat=repeat, outcome=outcome,
        failure_step=None if outcome == "success" else step, checks=[], fidelity_rate=1, user_turns=1,
        judge={"task_completed": DimConsensus(label="yes", agreement=0.5, n_valid=2, labels=["yes", "no"])},
    )


def test_grades_follow_the_rubric():
    rubric = load_grade_rubric()
    assert compute_grade(1.0, {}, 4, 4, rubric)[0] == "A"
    grade, reasons = compute_grade(0.8, {"silent_failure_any": True}, 5, 5, rubric)
    assert grade == "C"
    assert "wasn't" in reasons[0]
    capped, _reasons = compute_grade(1.0, {"forbidden_critical_any": True}, 4, 4, rubric)
    assert capped == "D"
    withheld, why = compute_grade(None, {}, 0, 4, rubric)
    assert withheld is None
    assert why[0].startswith("No deterministic")


def test_pass_hat_flaky_and_failure_order():
    pack = load_pack("core-en")
    rubric, _sha = load_rubric("gauntlet_v1")
    convs = [
        _conv("three-word-answerer", 0, "success"),
        _conv("three-word-answerer", 1, "success"),
        _conv("apologetic-novice", 0, "silent_failure"),
        _conv("apologetic-novice", 1, "abandoned", "ask_order"),
        _conv("mind-changer", 0, "silent_failure"),
        _conv("mind-changer", 1, "silent_failure"),
    ]
    scores = aggregate(convs, pack, rubric, 2, "complete")
    assert scores.pass_hat_k["personas_all_pass"] == 1
    flaky = next(row for row in scores.persona_rows if row.persona_id == "apologetic-novice")
    assert flaky.flaky is True
    assert scores.failure_steps[0].step == "confirm_address"
    assert scores.failure_steps[0].personas == ["apologetic-novice", "mind-changer"]
    assert "task_completed" in scores.unstable_dims


def test_silent_failure_fools_the_judge():
    pack = load_pack("core-en")
    scenario = load_scenario("demo")
    transcript = Transcript(
        conversation_id="pat--r0", persona_id="apologetic-novice", scenario_id=scenario.id, repeat=0, seed=1,
        remembered_facts={},
        turns=[
            Turn(index=1, role="user", text="yes please"),
            Turn(index=2, role="bot", text="Done! Your delivery address has been updated.", step="confirm_address"),
        ],
        end_reason="persona_done",
        final_state={"orders": {"A1001": {"address": "12 Oak Street"}}, "refunds": {}},
    )
    scored = score_conversation(transcript, scenario, _judge("yes"), 0, pack)
    assert scored.outcome == "silent_failure"
    assert scored.disagreements[0].note.startswith("**Fooled the judge too:")
    assert "orders.A1001.address" in scored.highlight["state_note"]
