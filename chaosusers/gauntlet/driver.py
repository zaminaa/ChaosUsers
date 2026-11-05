import random
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from chaosusers.engine.events import detect_events
from chaosusers.engine.fidelity import check_fidelity
from chaosusers.engine.operators import apply_operators
from chaosusers.engine.persona import (
    Directive,
    PersonaInstance,
    language_examples,
    language_instruction,
    next_directives,
)
from chaosusers.engine.prompts import render
from chaosusers.engine.state import PatienceState
from chaosusers.gauntlet.scenario import MindChange, Scenario, funnel_index, match_step
from chaosusers.gauntlet.targets import Target, TargetError
from chaosusers.llm.budget import BudgetExceeded
from chaosusers.llm.client import LLMClient
from chaosusers.llm.types import LLMRequest, Message
from chaosusers.packs.schema import Pack


class Turn(BaseModel):
    index: int
    role: Literal["user", "bot", "system_marker"]
    text: str
    raw_text: str | None = None
    step: str | None = None
    events: list[str] = []
    patience_after: float | None = None
    mood: str | None = None
    directives: list[str] = []
    fidelity_violations: list[str] = []


class Transcript(BaseModel):
    conversation_id: str
    persona_id: str
    scenario_id: str
    repeat: int
    seed: int
    remembered_facts: dict[str, str]
    applied_mind_changes: list[MindChange] = []
    turns: list[Turn]
    end_reason: Literal["persona_done", "abandoned", "turn_cap", "budget_exhausted", "target_error"]
    abandon_action: Literal["leave", "block", "go_silent", "demand_human"] | None = None
    final_state: dict | None = None
    persona_cost_usd: float = 0.0
    error: str | None = None


class PersonaOutput(BaseModel):
    message: str
    status: Literal["continue", "done"]


def run_conversation(
    inst: PersonaInstance,
    scenario: Scenario,
    target: Target,
    client: LLMClient,
    pack: Pack,
    model: str,
    max_turns: int,
    repeat: int,
    run_id: str,
    on_turn: Callable[[Turn], None] | None = None,
) -> Transcript:
    behavior = inst.spec.gauntlet
    if behavior is None:
        raise ValueError("gauntlet persona is required")
    session_id = f"{run_id}-{inst.spec.id}-r{repeat}"
    target.start(session_id)
    patience = PatienceState(spec=behavior.patience, value=behavior.patience.start)
    turns: list[Turn] = []
    fired = {"mind_change": 0, "scope_push": 0}
    steps_fired: set[str] = set()
    last_step: str | None = None
    max_step_idx = -1
    end_reason: str | None = None
    error: str | None = None
    abandon_action = None
    applied: list[MindChange] = []
    spent_before = client.budget.spent_usd

    def add(turn: Turn) -> None:
        turns.append(turn)
        if on_turn is not None:
            on_turn(turn)

    def persona_output(user_turn_no: int, directives: list[Directive], extra: list[Message]) -> PersonaOutput:
        system, user = render(
            "persona_gauntlet_v1",
            p=inst.spec,
            language_instruction=language_instruction(pack, inst.spec.language),
            language_examples=language_examples(pack, inst.spec.language),
            scenario=scenario,
            facts=inst.remembered_facts,
            mood=patience.mood,
            directives=directives,
            turns=turns,
        )
        request = LLMRequest(
            purpose="persona",
            tag=f"persona:{inst.spec.id}:r{repeat}",
            model=model,
            messages=[Message(role="system", content=system), Message(role="user", content=user), *extra],
            temperature=0.9,
            max_tokens=300,
            seed=inst.seed + user_turn_no,
        )
        return client.complete_json(request, PersonaOutput.model_validate)

    for user_turn_no in range(1, max_turns + 1):
        if patience.abandoned:
            action = behavior.patience.on_abandon
            abandon_action = action
            if action in {"block", "go_silent"}:
                marker = "[user blocked the bot]" if action == "block" else "[user stopped responding]"
                add(Turn(index=len(turns) + 1, role="system_marker", text=marker))
            else:
                text = behavior.patience.abandon_line
                raw = None
                if not text:
                    try:
                        produced = persona_output(user_turn_no, [Directive(kind="abandon", action=action)], [])
                        raw = produced.message
                        text = _shape(produced.message, inst, pack, patience.mood, user_turn_no)
                    except BudgetExceeded:
                        end_reason = "budget_exhausted"
                        break
                _send_pair(
                    add, turns, target, session_id, text or "", raw, patience, scenario, behavior,
                    last_step, max_step_idx, user_turn_no, [], [],
                )
            end_reason = "abandoned"
            break
        directives = next_directives(inst, scenario, user_turn_no, last_step, fired, steps_fired)
        for directive in directives:
            if directive.kind != "mind_change":
                continue
            for change in scenario.mind_changes:
                if change.fact == directive.fact and change.to == directive.to:
                    applied.append(change)
                    break
        try:
            produced = persona_output(user_turn_no, directives, [])
        except BudgetExceeded:
            end_reason = "budget_exhausted"
            break
        text = _shape(produced.message, inst, pack, patience.mood, user_turn_no)
        violations = check_fidelity(text, inst.spec)
        if violations:
            try:
                produced = persona_output(
                    user_turn_no,
                    directives,
                    [Message(role="user", content=f"Your last message broke character: {violations}. Rewrite it.")],
                )
            except BudgetExceeded:
                end_reason = "budget_exhausted"
                break
            text = _shape(produced.message, inst, pack, patience.mood, user_turn_no)
            violations = check_fidelity(text, inst.spec)
        mood_now = patience.mood
        kinds = [directive.kind for directive in directives]
        if produced.status == "done":
            add(Turn(index=len(turns) + 1, role="user", text=text, raw_text=produced.message, mood=mood_now, directives=kinds, fidelity_violations=violations))
            end_reason = "persona_done"
            break
        try:
            reply = target.send(session_id, text, turns)
        except TargetError as exc:
            add(Turn(index=len(turns) + 1, role="user", text=text, raw_text=produced.message, mood=mood_now, directives=kinds, fidelity_violations=violations))
            end_reason = "target_error"
            error = str(exc)
            break
        matched = match_step(scenario, reply.text)
        step_id = matched.id if matched else last_step
        step_index = funnel_index(scenario, matched.id) if matched and matched.funnel else None
        prior_bots = [turn.text for turn in turns if turn.role == "bot"]
        prior_users = [turn.text for turn in turns if turn.role == "user"]
        prior_users.append(text)
        events = detect_events(
            reply.text, prior_bots, prior_users, scenario.fallback_patterns, scenario.facts,
            step_index, max_step_idx, behavior.reading_budget_words,
        )
        add(Turn(index=len(turns) + 1, role="user", text=text, raw_text=produced.message, mood=mood_now, directives=kinds, fidelity_violations=violations))
        patience.apply(events)
        add(Turn(index=len(turns) + 1, role="bot", text=reply.text, step=step_id, events=list(events), patience_after=patience.value))
        if step_index is not None and step_index > max_step_idx:
            max_step_idx = step_index
        last_step = step_id
    else:
        end_reason = "turn_cap"

    final_state = None
    if target.has_state:
        try:
            final_state = target.state(session_id)
        except TargetError as exc:
            error = error or str(exc)
    return Transcript(
        conversation_id=f"{inst.spec.id}--r{repeat}",
        persona_id=inst.spec.id,
        scenario_id=scenario.id,
        repeat=repeat,
        seed=inst.seed,
        remembered_facts=inst.remembered_facts,
        applied_mind_changes=applied,
        turns=turns,
        end_reason=end_reason or "turn_cap",
        abandon_action=abandon_action,
        final_state=final_state,
        persona_cost_usd=client.budget.spent_usd - spent_before,
        error=error,
    )


def _shape(message: str, inst: PersonaInstance, pack: Pack, mood: str, user_turn_no: int) -> str:
    behavior = inst.spec.gauntlet
    rng = random.Random(inst.seed * 1000 + user_turn_no)
    return apply_operators(message, behavior.operators if behavior else [], mood, rng, pack.lexicon)


def _send_pair(add, turns, target, session_id, text, raw, patience, scenario, behavior, last_step, max_step_idx, user_turn_no, kinds, violations):
    reply = target.send(session_id, text, turns)
    matched = match_step(scenario, reply.text)
    step_id = matched.id if matched else last_step
    events = detect_events(
        reply.text,
        [turn.text for turn in turns if turn.role == "bot"],
        [turn.text for turn in turns if turn.role == "user"],
        scenario.fallback_patterns,
        scenario.facts,
        None,
        max_step_idx,
        behavior.reading_budget_words,
    )
    add(Turn(index=len(turns) + 1, role="user", text=text, raw_text=raw, mood=patience.mood, directives=kinds, fidelity_violations=violations))
    patience.apply(events)
    add(Turn(index=len(turns) + 1, role="bot", text=reply.text, step=step_id, events=list(events), patience_after=patience.value))

