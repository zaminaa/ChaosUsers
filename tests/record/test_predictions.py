from chaosusers.gauntlet.score import ConversationScore, GauntletScores, PersonaRow, StepFailure
from chaosusers.packs.loader import load_pack, load_taxonomy
from chaosusers.record.predictions import canonical_sha256, predictions_from_gauntlet
from chaosusers.record.schema import Prediction


def _score(persona: str, repeat: int, outcome: str) -> ConversationScore:
    return ConversationScore(
        conversation_id=f"{persona}--r{repeat}", persona_id=persona, repeat=repeat, outcome=outcome,
        failure_step="confirm_address", checks=[], fidelity_rate=1, user_turns=1,
    )


def test_hash_is_stable_and_predictions_are_capped():
    left = Prediction(id="P-001", kind="location", claim="Step confirm_address will be among the top 3 drop-off points of this flow in production.", check_hint="hint", support="3/3", confidence="high", evidence=[], step_id="confirm_address", top_k=3)
    right = Prediction.model_validate({"confidence": "high", "evidence": [], "support": "3/3", "check_hint": "hint", "claim": left.claim, "kind": "location", "id": "P-001", "step_id": "confirm_address", "top_k": 3})
    assert canonical_sha256(left) == canonical_sha256(right)
    changed = left.model_copy(update={"claim": left.claim + "!"})
    assert canonical_sha256(changed) != canonical_sha256(left)

    pack = load_pack("core-en")
    personas = ["three-word-answerer", "apologetic-novice", "mind-changer"]
    convs = [_score(persona, repeat, "silent_failure") for persona in personas for repeat in (0, 1)]
    extra = []
    for index in range(8):
        extra.append(ConversationScore(
            conversation_id=f"x{index}--r0", persona_id="scope-pusher", repeat=0, outcome="stuck",
            failure_step=f"step-{index}", checks=[], fidelity_rate=1, user_turns=1,
        ))
    scores = GauntletScores(
        grade="C", grade_reasons=[], success_rate=0, pass_hat_k={"k": 2, "personas_all_pass": 0, "personas_total": 4},
        outcomes={"silent_failure": 6}, silent_failures=6, forbidden=[],
        failure_steps=[StepFailure(step="confirm_address", personas=personas, conversations=6)] + [
            StepFailure(step=f"step-{index}", personas=["scope-pusher"], conversations=1) for index in range(8)
        ],
        persona_rows=[
            PersonaRow(persona_id=persona, name=pack.personas[persona].name, archetype=pack.personas[persona].archetype,
                       behavior_class=pack.personas[persona].behavior_class, outcomes=["silent_failure", "silent_failure"],
                       pass_all=False, flaky=False)
            for persona in personas
        ],
        judge_stability={}, unstable_dims=[], ungrounded_samples=0, disagreements_total=0, fidelity_rate=1,
        conversations=convs + extra, status="complete",
    )
    predicted = predictions_from_gauntlet(scores, None, pack, load_taxonomy(), "run", "AcmeBot")
    assert predicted.predictions[0].id == "P-001"
    assert predicted.predictions[0].kind == "location"
    assert predicted.predictions[0].confidence == "high"
    assert predicted.predictions[0].top_k == 3
    assert any(item.failure_type == "silent_failure" for item in predicted.predictions)
    assert len(predicted.predictions) <= 10
    assert [item.id for item in predicted.predictions] == [f"P-{index:03d}" for index in range(1, len(predicted.predictions) + 1)]
