import re

from pydantic import BaseModel

from chaosusers.gauntlet.driver import Transcript
from chaosusers.gauntlet.scenario import CheckSpec, Scenario, effective_match_tokens

_MISSING = object()


class CheckResult(BaseModel):
    check_id: str
    kind: str
    severity: str
    passed: bool | None
    detail: str
    description: str = ""


def get_path(state, path: str):
    current = state
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return _MISSING
            current = current[part]
            continue
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return _MISSING
            continue
        return _MISSING
    return current


def evaluate_checks(scenario: Scenario, transcript: Transcript) -> list[CheckResult]:
    return [_one(check, scenario, transcript) for check in scenario.checks]


def _one(check: CheckSpec, scenario: Scenario, transcript: Transcript) -> CheckResult:
    if check.type.startswith("state_") and transcript.final_state is None:
        return _result(check, None, "state unavailable")
    if check.type == "state_equals":
        found = get_path(transcript.final_state, check.path or "")
        return _result(check, found == check.value, f"found {found!r}")
    if check.type == "state_tokens":
        found = get_path(transcript.final_state, check.path or "")
        if found is _MISSING:
            return _result(check, None, "path missing")
        wanted = effective_match_tokens(scenario, check.fact or "", transcript.applied_mind_changes)
        have = {token.lower() for token in re.findall(r"[A-Za-z0-9]+", str(found))}
        passed = all(token.lower() in have for token in wanted)
        return _result(check, passed, f"wanted {wanted}")
    if check.type == "state_absent":
        found = get_path(transcript.final_state, check.path or "")
        return _result(check, found is _MISSING, "present" if found is not _MISSING else "absent")
    if check.type == "state_empty":
        found = get_path(transcript.final_state, check.path or "")
        return _result(check, found is _MISSING or found in ({}, [], None), f"found {found!r}")
    if check.type == "bot_matches":
        hit = any(turn.role == "bot" and re.search(check.pattern or "", turn.text, re.IGNORECASE) for turn in transcript.turns)
        return _result(check, hit, "matched" if hit else "no match")
    if check.type == "bot_never_matches":
        hit = any(turn.role == "bot" and re.search(check.pattern or "", turn.text, re.IGNORECASE) for turn in transcript.turns)
        return _result(check, not hit, "forbidden text present" if hit else "clear")
    user_turns = sum(turn.role == "user" for turn in transcript.turns)
    return _result(check, user_turns <= (check.n or 0), f"{user_turns} user turns")


def _result(check: CheckSpec, passed: bool | None, detail: str) -> CheckResult:
    return CheckResult(
        check_id=check.id, kind=check.kind, severity=check.severity, passed=passed, detail=detail, description=check.description
    )
