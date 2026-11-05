import random
from typing import Any, Literal

from pydantic import BaseModel

from chaosusers.packs.schema import Pack, PersonaSpec


class Directive(BaseModel):
    kind: Literal["mind_change", "scope_push", "abandon"]
    fact: str | None = None
    to: str | None = None
    request: str | None = None
    action: str | None = None


class PersonaInstance(BaseModel):
    spec: PersonaSpec
    seed: int
    remembered_facts: dict[str, str] = {}
    overrides: dict = {}


def language_instruction(pack: Pack, language: str) -> str:
    return pack.meta.language_instructions[language]


def language_examples(pack: Pack, language: str) -> list[str]:
    return pack.lexicon.examples_by_language.get(language, [])


def build_instance(spec: PersonaSpec, seed: int, scenario: Any) -> PersonaInstance:
    remembered: dict[str, str] = {}
    facts = getattr(scenario, "facts", None) if scenario is not None else None
    if facts and spec.gauntlet is not None:
        rng = random.Random(seed)
        for name in sorted(facts):
            fact = facts[name]
            if fact.variants and rng.random() < spec.gauntlet.fact_drift:
                remembered[name] = rng.choice(fact.variants)
            else:
                remembered[name] = fact.value
    return PersonaInstance(spec=spec, seed=seed, remembered_facts=remembered)


def next_directives(
    inst: PersonaInstance,
    scenario: Any,
    user_turn_no: int,
    last_bot_step: str | None,
    fired: dict[str, int],
    steps_fired: set[str],
) -> list[Directive]:
    directives: list[Directive] = []
    behavior = inst.spec.gauntlet
    if behavior is None or scenario is None:
        return directives
    change = behavior.mind_change
    if change is not None:
        ready = fired["mind_change"] < change.count and fired["mind_change"] < len(scenario.mind_changes)
        at_commitment = change.at == "commitment" and last_bot_step in scenario.commitment_steps and last_bot_step not in steps_fired
        at_turn = change.at == "turns" and user_turn_no in change.turns
        if ready and (at_commitment or at_turn):
            item = scenario.mind_changes[fired["mind_change"]]
            directives.append(Directive(kind="mind_change", fact=item.fact, to=item.to))
            fired["mind_change"] += 1
            if last_bot_step is not None:
                steps_fired.add(last_bot_step)
    push = behavior.scope_push
    if (
        push is not None
        and user_turn_no in push.turns
        and fired["scope_push"] < push.attempts
        and fired["scope_push"] < len(scenario.scope_requests)
    ):
        directives.append(Directive(kind="scope_push", request=scenario.scope_requests[fired["scope_push"]]))
        fired["scope_push"] += 1
    return directives
