import hashlib
import re
from typing import Any

import yaml
from pydantic import BaseModel

from chaosusers.paths import resolve_data_path


class FactSpec(BaseModel):
    value: str
    variants: list[str] = []
    match_tokens: list[str]
    asked_by: str | None = None
    label: str | None = None


class MindChange(BaseModel):
    fact: str
    to: str
    match_tokens: list[str]


class StepSpec(BaseModel):
    id: str
    bot_matches: str
    funnel: bool = True


class CheckSpec(BaseModel):
    id: str
    kind: str
    severity: str = "major"
    type: str
    path: str | None = None
    value: Any = None
    fact: str | None = None
    pattern: str | None = None
    n: int | None = None
    description: str


class Scenario(BaseModel):
    id: str
    version: int
    title: str
    context: str
    task: str
    facts: dict[str, FactSpec]
    mind_changes: list[MindChange] = []
    scope_requests: list[str] = []
    steps: list[StepSpec]
    commitment_steps: list[str] = []
    success_claim: str
    fallback_patterns: list[str]
    checks: list[CheckSpec]
    max_turns: int | None = None
    sha256: str = ""


def load_scenario(spec: str) -> Scenario:
    path = resolve_data_path("scenarios/acme/change_address.yaml" if spec == "demo" else spec)
    scenario = Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    _validate(scenario)
    scenario.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return scenario


def effective_match_tokens(scenario: Scenario, fact: str, applied_changes: list[MindChange]) -> list[str]:
    tokens = scenario.facts[fact].match_tokens
    for change in applied_changes:
        if change.fact == fact:
            tokens = change.match_tokens
    return tokens


def match_step(scenario: Scenario, bot_text: str) -> StepSpec | None:
    for step in scenario.steps:
        if re.search(step.bot_matches, bot_text, re.IGNORECASE):
            return step
    return None


def funnel_index(scenario: Scenario, step_id: str) -> int | None:
    index = 0
    for step in scenario.steps:
        if not step.funnel:
            continue
        if step.id == step_id:
            return index
        index += 1
    return None


def _validate(scenario: Scenario) -> None:
    step_ids = {step.id for step in scenario.steps}
    for step_id in scenario.commitment_steps:
        if step_id not in step_ids:
            raise ValueError(f"commitment_steps: unknown step {step_id}")
    for check in scenario.checks:
        if check.fact is not None and check.fact not in scenario.facts:
            raise ValueError(f"fact: unknown fact {check.fact}")
        if check.type.startswith("state_") and not check.path:
            raise ValueError(f"path: {check.id} requires path")
        if check.pattern is not None:
            _compile("pattern", check.pattern)
    for step in scenario.steps:
        _compile("bot_matches", step.bot_matches)
    _compile("success_claim", scenario.success_claim)
    for pattern in scenario.fallback_patterns:
        _compile("fallback_patterns", pattern)
    for fact in scenario.facts.values():
        if fact.asked_by:
            _compile("asked_by", fact.asked_by)


def _compile(field: str, pattern: str) -> None:
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"{field}: {exc}") from exc
