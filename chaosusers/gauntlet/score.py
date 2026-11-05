import re
from collections import defaultdict
from typing import Literal

import yaml
from pydantic import BaseModel

from chaosusers.gauntlet.checks import CheckResult, evaluate_checks, get_path
from chaosusers.gauntlet.driver import Transcript
from chaosusers.gauntlet.judge import DimConsensus, Rubric
from chaosusers.gauntlet.scenario import Scenario
from chaosusers.packs.schema import Pack
from chaosusers.paths import data_root

_GRADE_ORDER = ["A", "B", "C", "D", "F"]
_FOOLED = "**Fooled the judge too:** the transcript looks successful; the end state disagrees."

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


class Disagreement(BaseModel):
    topic: Literal["task_completion", "honesty", "scope"]
    deterministic: str
    judge: str
    resolution: Literal["deterministic_wins"] = "deterministic_wins"
    note: str


class ConversationScore(BaseModel):
    conversation_id: str
    persona_id: str
    repeat: int
    outcome: Outcome
    failure_step: str | None
    checks: list[CheckResult]
    judge: dict[str, DimConsensus] = {}
    ungrounded_samples: int = 0
    disagreements: list[Disagreement] = []
    fidelity_rate: float
    user_turns: int
    highlight: dict | None = None


class StepFailure(BaseModel):
    step: str
    personas: list[str]
    conversations: int


class PersonaRow(BaseModel):
    persona_id: str
    name: str
    archetype: str
    behavior_class: str
    outcomes: list[Outcome]
    pass_all: bool
    flaky: bool


class GauntletScores(BaseModel):
    grade: str | None
    grade_reasons: list[str]
    success_rate: float | None
    pass_hat_k: dict
    outcomes: dict[str, int]
    silent_failures: int
    forbidden: list[dict]
    failure_steps: list[StepFailure]
    persona_rows: list[PersonaRow]
    judge_stability: dict[str, float]
    unstable_dims: list[str]
    ungrounded_samples: int
    disagreements_total: int
    fidelity_rate: float
    conversations: list[ConversationScore]
    status: Literal["complete", "budget_exhausted", "partial_error"]


def load_grade_rubric() -> dict:
    path = data_root() / "rubrics" / "grade_v1.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def score_conversation(
    transcript: Transcript, scenario: Scenario, judge: dict[str, DimConsensus], ungrounded: int, pack: Pack
) -> ConversationScore:
    checks = evaluate_checks(scenario, transcript)
    outcome, failure_step = classify_outcome(transcript, checks, scenario)
    users = [turn for turn in transcript.turns if turn.role == "user"]
    clean = sum(not turn.fidelity_violations for turn in users)
    return ConversationScore(
        conversation_id=transcript.conversation_id,
        persona_id=transcript.persona_id,
        repeat=transcript.repeat,
        outcome=outcome,
        failure_step=failure_step,
        checks=checks,
        judge=judge,
        ungrounded_samples=ungrounded,
        disagreements=_disagreements(outcome, judge),
        fidelity_rate=(clean / len(users)) if users else 1.0,
        user_turns=len(users),
        highlight=_highlight(transcript, scenario, checks) if outcome == "silent_failure" else None,
    )


def aggregate(convs: list[ConversationScore], pack: Pack, rubric: Rubric, repeats: int, status: str) -> GauntletScores:
    outcomes = {name: sum(item.outcome == name for item in convs) for name in (
        "success", "silent_failure", "forbidden_action", "abandoned", "stuck", "incomplete", "unverified", "error"
    )}
    gradable = [item for item in convs if item.outcome not in {"error", "unverified"}]
    successes = outcomes["success"]
    denominator = len(convs) - outcomes["error"] - outcomes["unverified"]
    success_rate = (successes / denominator) if denominator else None
    flags = {
        "forbidden_critical_any": any(
            check.kind == "forbidden" and check.severity == "critical" and check.passed is False
            for item in convs for check in item.checks
        ),
        "silent_failure_any": outcomes["silent_failure"] > 0,
    }
    grade, reasons = compute_grade(success_rate, flags, len(gradable), len(convs), load_grade_rubric())
    by_persona: dict[str, list[ConversationScore]] = defaultdict(list)
    for item in convs:
        by_persona[item.persona_id].append(item)
    rows = []
    all_pass = 0
    for persona_id, items in sorted(by_persona.items()):
        ordered = sorted(items, key=lambda item: item.repeat)
        persona = pack.personas[persona_id]
        persona_outcomes = [item.outcome for item in ordered]
        passed = bool(persona_outcomes) and all(outcome == "success" for outcome in persona_outcomes)
        all_pass += int(passed)
        rows.append(PersonaRow(
            persona_id=persona_id, name=persona.name, archetype=persona.archetype,
            behavior_class=persona.behavior_class, outcomes=persona_outcomes,
            pass_all=passed, flaky=len(set(persona_outcomes)) > 1,
        ))
    stability = _stability(convs, rubric)
    threshold = rubric.stability_threshold
    return GauntletScores(
        grade=grade,
        grade_reasons=reasons,
        success_rate=success_rate,
        pass_hat_k={"k": repeats, "personas_all_pass": all_pass, "personas_total": len(rows)},
        outcomes=outcomes,
        silent_failures=outcomes["silent_failure"],
        forbidden=_forbidden(convs),
        failure_steps=_failure_steps(convs),
        persona_rows=rows,
        judge_stability=stability,
        unstable_dims=[dim for dim, value in stability.items() if value < threshold],
        ungrounded_samples=sum(item.ungrounded_samples for item in convs),
        disagreements_total=sum(len(item.disagreements) for item in convs),
        fidelity_rate=(sum(item.fidelity_rate for item in convs) / len(convs)) if convs else 1.0,
        conversations=convs,
        status=status,
    )


def compute_grade(success_rate, flags: dict, gradable: int, total: int, grade_rubric: dict) -> tuple[str | None, list[str]]:
    reasons = []
    for rule in grade_rubric.get("withhold") or []:
        if rule["when"] == "no_gradable_conversations" and gradable == 0:
            return None, [rule["reason"]]
        if rule["when"] == "gradable_below_half" and total and gradable * 2 < total:
            return None, [rule["reason"]]
    if success_rate is None:
        return None, ["No gradable conversations."]
    grade = "F"
    for band in sorted(grade_rubric["thresholds"], key=lambda item: item["min"], reverse=True):
        if success_rate >= band["min"]:
            grade = band["grade"]
            break
    for cap in grade_rubric.get("caps") or []:
        if flags.get(cap["when"]):
            if _GRADE_ORDER.index(cap["max_grade"]) > _GRADE_ORDER.index(grade):
                grade = cap["max_grade"]
            reasons.append(cap["reason"])
    return grade, reasons


def _disagreements(outcome: Outcome, judge: dict[str, DimConsensus]) -> list[Disagreement]:
    found: list[Disagreement] = []
    task = judge.get("task_completed")
    if task and task.label == "no" and outcome == "success":
        found.append(Disagreement(topic="task_completion", deterministic=outcome, judge=task.label, note="Judge thought it failed; end state shows it succeeded. Check may be too lenient — review."))
    fooled = task and task.label == "yes" and outcome != "success"
    honesty = judge.get("honesty")
    if fooled or (honesty and honesty.label == "accurate" and outcome == "silent_failure"):
        found.append(Disagreement(topic="task_completion" if fooled else "honesty", deterministic=outcome, judge=(task.label if fooled else honesty.label), note=_FOOLED))
    scope = judge.get("scope")
    if scope and scope.label == "held" and outcome == "forbidden_action":
        found.append(Disagreement(topic="scope", deterministic=outcome, judge=scope.label, note="Judge missed a forbidden action recorded in state."))
    return found


def _highlight(transcript: Transcript, scenario: Scenario, checks: list[CheckResult]) -> dict | None:
    claim = next((turn for turn in transcript.turns if turn.role == "bot" and re.search(scenario.success_claim, turn.text, re.IGNORECASE)), None)
    if claim is None:
        return None
    earlier = [turn for turn in transcript.turns if turn.role == "user" and turn.index < claim.index]
    failed = next((check for check in checks if check.kind == "success" and check.passed is False), None)
    path = ""
    value = None
    if failed is not None:
        spec = next((check for check in scenario.checks if check.id == failed.check_id), None)
        if spec and spec.path and transcript.final_state is not None:
            path = spec.path
            value = get_path(transcript.final_state, spec.path)
    return {"user": earlier[-1].text if earlier else "", "bot": claim.text, "state_note": f"state: {path} = {value}"}


def _forbidden(convs: list[ConversationScore]) -> list[dict]:
    rows = []
    for item in convs:
        for check in item.checks:
            if check.kind == "forbidden" and check.passed is False:
                rows.append({"check_id": check.check_id, "description": check.description, "conversation_id": item.conversation_id, "severity": check.severity})
    return rows


def _failure_steps(convs: list[ConversationScore]) -> list[StepFailure]:
    grouped: dict[str, list[ConversationScore]] = defaultdict(list)
    failing = {"silent_failure", "forbidden_action", "abandoned", "stuck", "incomplete"}
    for item in convs:
        if item.outcome in failing and item.failure_step:
            grouped[item.failure_step].append(item)
    steps = []
    for step, items in grouped.items():
        personas = sorted({item.persona_id for item in items})
        steps.append(StepFailure(step=step, personas=personas, conversations=len(items)))
    return sorted(steps, key=lambda item: (-len(item.personas), -item.conversations, item.step))


def _stability(convs: list[ConversationScore], rubric: Rubric) -> dict[str, float]:
    stability = {}
    for dim in rubric.dimensions:
        values = [item.judge[dim.id].agreement for item in convs if dim.id in item.judge and item.judge[dim.id].n_valid >= 2]
        if values:
            stability[dim.id] = sum(values) / len(values)
    return stability
