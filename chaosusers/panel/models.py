from typing import Literal

from pydantic import BaseModel, Field


class Finding(BaseModel):
    section_id: str
    type: Literal["confused", "abandon", "misunderstood", "objection", "skip"]
    artifact_quote: str
    in_character_quote: str
    explanation: str
    severity: Literal[1, 2, 3]
    grounded: bool = False
    ungrounded_reason: str | None = None


class PanelOutput(BaseModel):
    verdict: Literal["would_complete", "would_abandon", "would_not_start"]
    abandon_at: str | None = None
    first_impression: str
    findings: list[Finding] = Field(min_length=1, max_length=6)


class PanelResponse(BaseModel):
    persona_id: str
    repeat: int
    output: PanelOutput | None
    valid: bool
    error: str | None = None
    words_read: int
