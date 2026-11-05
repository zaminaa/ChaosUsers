from typing import Literal

from pydantic import BaseModel

from chaosusers.gauntlet.scenario import MindChange


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
