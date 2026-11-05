from chaosusers.gauntlet.checks import CheckResult
from chaosusers.gauntlet.driver import Transcript, Turn
from chaosusers.gauntlet.scenario import load_scenario
from chaosusers.gauntlet.score import classify_outcome


def _transcript(end_reason="persona_done", state=None, bots=None) -> Transcript:
    turns = [Turn(index=index, role="bot", text=text, step="confirm_address") for index, text in enumerate(bots or ["ok"], start=1)]
    return Transcript(
        conversation_id="t--r0",
        persona_id="t",
        scenario_id="s",
        repeat=0,
        seed=1,
        remembered_facts={},
        turns=turns,
        end_reason=end_reason,
        final_state=state,
    )


def _check(kind, passed, check_id="c") -> CheckResult:
    return CheckResult(check_id=check_id, kind=kind, severity="critical", passed=passed, detail="")


def test_precedence_and_end_states():
    scenario = load_scenario("demo")
    done = "Done! Your delivery address has been updated."
    assert classify_outcome(_transcript("budget_exhausted", bots=[done]), [_check("success", False)], scenario)[0] == "error"
    assert classify_outcome(_transcript(state={"a": 1}, bots=[done]), [_check("forbidden", False), _check("success", False)], scenario)[0] == "forbidden_action"
    assert classify_outcome(_transcript(state={"a": 1}, bots=[done]), [_check("success", False)], scenario)[0] == "silent_failure"
    assert classify_outcome(_transcript(state={"a": 1}, bots=["hello"]), [_check("success", True)], scenario) == ("success", None)
    assert classify_outcome(_transcript(bots=[done]), [_check("success", None)], scenario)[0] == "unverified"
    assert classify_outcome(_transcript("abandoned", state={"a": 1}, bots=["hello"]), [_check("success", False)], scenario)[0] == "abandoned"
    assert classify_outcome(_transcript("turn_cap", state={"a": 1}, bots=["hello"]), [_check("success", False)], scenario)[0] == "stuck"
    assert classify_outcome(_transcript("persona_done", state={"a": 1}, bots=["hello"]), [_check("success", False)], scenario)[0] == "incomplete"
