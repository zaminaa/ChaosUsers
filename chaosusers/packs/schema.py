import re
from typing import Literal

from pydantic import BaseModel, model_validator

Mood = Literal["calm", "frustrated", "angry"]
EventName = Literal["turn", "bot_fallback", "bot_repeated", "bot_long", "bot_asks_known_fact", "bot_progress"]
_KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class BehaviorClass(BaseModel):
    id: str
    name: str
    description: str
    production_signals: list[str]
    typical_failures: list[str]
    respect_note: str
    personas_welcome: bool = True


class VoiceSpec(BaseModel):
    register: str
    vocabulary_level: Literal["plain", "everyday", "technical"]
    typical_phrases: list[str]
    never: list[str] = []
    example_utterance: str


class OperatorSpec(BaseModel):
    op: Literal["max_words", "lowercase", "uppercase", "strip_punctuation", "exclaim", "typos", "apology_prefix"]
    p: float = 1.0
    when_mood: list[Mood] = ["calm", "frustrated", "angry"]
    n: int | None = None
    rate: float | None = None


class PatienceSpec(BaseModel):
    start: float
    costs: dict[EventName, float] = {}
    recovery: dict[EventName, float] = {}
    frustrated_below: float
    angry_below: float
    abandon_at: float = 0.0
    on_abandon: Literal["leave", "block", "go_silent", "demand_human"] = "leave"
    abandon_line: str | None = None


class MindChangeSpec(BaseModel):
    count: int
    at: Literal["commitment", "turns"]
    turns: list[int] = []


class ScopePushSpec(BaseModel):
    attempts: int
    turns: list[int]


class GauntletBehavior(BaseModel):
    reading_budget_words: int
    fact_drift: float
    patience: PatienceSpec
    operators: list[OperatorSpec] = []
    mind_change: MindChangeSpec | None = None
    scope_push: ScopePushSpec | None = None


class ReadingSpec(BaseModel):
    mode: Literal["full", "skim"]
    words_per_section: int | None = None


class PanelBehavior(BaseModel):
    reading: ReadingSpec
    attention_focus: list[str]
    abandon_triggers: list[str]
    extra_instructions: list[str] = []


class FidelitySpec(BaseModel):
    max_words: int | None = None
    require_script: Literal["any", "Latin", "Arabic"] = "any"
    forbidden_words: list[str] = []


class PersonaSpec(BaseModel):
    id: str
    name: str
    archetype: str
    behavior_class: str
    language: str
    summary: str
    trust_in_bot: Literal["credulous", "normal", "skeptical"] = "normal"
    voice: VoiceSpec
    modes: list[Literal["panel", "gauntlet"]]
    gauntlet: GauntletBehavior | None = None
    panel: PanelBehavior | None = None
    fidelity: FidelitySpec = FidelitySpec()

    @model_validator(mode="after")
    def _modes_and_id(self):
        if _KEBAB.match(self.id) is None:
            raise ValueError(f"id must be kebab-case: {self.id}")
        if "gauntlet" in self.modes and self.gauntlet is None:
            raise ValueError("modes includes gauntlet but gauntlet block is missing")
        if "panel" in self.modes and self.panel is None:
            raise ValueError("modes includes panel but panel block is missing")
        return self


class PackMeta(BaseModel):
    id: str
    version: str
    title: str
    language: str
    license: str
    extends: str | None = None
    provenance: str
    language_instructions: dict[str, str]


class Lexicon(BaseModel):
    language: str
    apology_phrases: list[str] = []
    examples_by_language: dict[str, list[str]] = {}


class Pack(BaseModel):
    meta: PackMeta
    lexicon: Lexicon
    personas: dict[str, PersonaSpec]
    sha256: str

    def for_mode(self, mode: str) -> list[PersonaSpec]:
        return sorted((persona for persona in self.personas.values() if mode in persona.modes), key=lambda persona: persona.id)
