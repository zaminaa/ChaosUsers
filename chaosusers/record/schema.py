from typing import Literal

from pydantic import BaseModel


class Manifest(BaseModel):
    run_id: str
    created_at: str
    chaosusers_version: str
    mode: Literal["gauntlet", "panel"]
    command: list[str]
    status: Literal["complete", "budget_exhausted", "partial_error"]
    replay_of: str | None = None
    scripted: bool = False
    provider: str
    persona_model: str
    judge_model: str | None = None
    settings: dict
    pack: dict
    personas: list[str]
    scenario: dict | None = None
    target: dict | None = None
    artifact: dict | None = None
    prompts: dict[str, str]
    rubric: dict | None = None
    cost: dict
    predictions_sha256: str


class Prediction(BaseModel):
    id: str
    kind: Literal["location", "occurs"]
    claim: str
    step_id: str | None = None
    top_k: int | None = None
    failure_type: str | None = None
    behavior_class: str | None = None
    check_hint: str
    support: str
    confidence: Literal["low", "medium", "high"]
    evidence: list[str]


class PredictionSet(BaseModel):
    run_id: str
    created_at: str
    mode: str
    subject: str
    predictions: list[Prediction]


class Observed(BaseModel):
    run_id: str
    observed_at: str
    source: str
    sessions: int | None = None
    dropoff_ranking: list[str] = []
    occurrences: dict[str, bool] = {}


class VerificationResult(BaseModel):
    id: str
    status: Literal["confirmed", "refuted", "untested"]
    note: str


class Verification(BaseModel):
    run_id: str
    verified_at: str
    receipt_intact: bool
    results: list[VerificationResult]
    confirmed: int
    refuted: int
    untested: int
    precision: float | None
