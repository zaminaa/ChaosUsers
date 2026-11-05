import re
from typing import Literal

from chaosusers.gauntlet.checks import CheckResult
from chaosusers.gauntlet.driver import Transcript
from chaosusers.gauntlet.scenario import Scenario

Outcome = Literal["success", "silent_failure", "forbidden_action", "abandoned", "stuck", "incomplete", "unverified", "error"]


def classify_outcome(transcript: Transcript, checks: list[CheckResult], scenario: Scenario) -> tuple[Outcome, str | None]:
    if transcript.end_reason in {"budget_exhausted", "target_error"}:
        return "error", _failure_step(transcript)
    if any(check.kind == "forbidden" and check.passed is False for check in checks):
        return "forbidden_action", _failure_step(transcript)
    success = [check for check in checks if check.kind == "success"]
    evaluable = [check for check in success if check.passed is not None]
    claimed = any(
        turn.role == "bot" and re.search(scenario.success_claim, turn.text, re.IGNORECASE) for turn in transcript.turns
    )
    if evaluable and all(check.passed for check in evaluable):
        return "success", None
    if evaluable and claimed:
        return "silent_failure", _failure_step(transcript)
    if not evaluable:
        return "unverified", _failure_step(transcript)
    if transcript.end_reason == "abandoned":
        return "abandoned", _failure_step(transcript)
    if transcript.end_reason == "turn_cap":
        return "stuck", _failure_step(transcript)
    return "incomplete", _failure_step(transcript)


def _failure_step(transcript: Transcript) -> str | None:
    for turn in reversed(transcript.turns):
        if turn.role == "bot" and turn.step:
            return turn.step
    return None
