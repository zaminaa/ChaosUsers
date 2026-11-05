import hashlib
from collections import Counter

import yaml
from pydantic import BaseModel

from chaosusers.engine.prompts import render
from chaosusers.gauntlet.driver import Transcript
from chaosusers.llm.client import LLMClient, LLMOutputError
from chaosusers.llm.types import LLMRequest, Message
from chaosusers.paths import data_root
from chaosusers.textutil import normalize


class LabelSpec(BaseModel):
    id: str
    definition: str
    example: str
    no_evidence: bool = False
    bad: bool = False


class DimensionSpec(BaseModel):
    id: str
    question: str
    deterministic_counterpart: str | None = None
    labels: list[LabelSpec]


class Rubric(BaseModel):
    id: str
    version: int
    applies_to: str
    stability_threshold: float
    dimensions: list[DimensionSpec]


class Evidence(BaseModel):
    turn: int
    quote: str


class DimJudgment(BaseModel):
    label: str
    evidence: list[Evidence] = []
    rationale: str = ""
    grounded: bool = False


class DimConsensus(BaseModel):
    label: str
    agreement: float
    n_valid: int
    labels: list[str]
    evidence: list[Evidence] = []


def load_rubric(rubric_id: str) -> tuple[Rubric, str]:
    path = data_root() / "rubrics" / f"{rubric_id}.yaml"
    raw = path.read_bytes()
    return Rubric.model_validate(yaml.safe_load(raw)), hashlib.sha256(raw).hexdigest()


def judge_transcript(
    transcript: Transcript,
    rubric: Rubric,
    client: LLMClient,
    model: str,
    samples: int,
    base_seed: int,
) -> tuple[dict[str, DimConsensus], int]:
    turns = [turn for turn in transcript.turns if turn.role in {"user", "bot", "system_marker"}]
    collected: dict[str, list[tuple[str, list[Evidence]]]] = {dim.id: [] for dim in rubric.dimensions}
    ungrounded = 0
    for sample in range(samples):
        system, user = render("judge_gauntlet_v1", rubric=rubric, turns=turns)
        request = LLMRequest(
            purpose="judge",
            tag=f"judge:{transcript.persona_id}:r{transcript.repeat}:s{sample}",
            model=model,
            messages=[Message(role="system", content=system), Message(role="user", content=user)],
            temperature=0.5,
            max_tokens=900,
            seed=base_seed + sample,
        )
        try:
            payload = client.complete_json(request, _identity)
        except LLMOutputError:
            ungrounded += 1
            continue
        if not _sample_valid(payload, rubric):
            ungrounded += 1
            continue
        for dim in rubric.dimensions:
            raw = payload[dim.id]
            evidence = [Evidence.model_validate(item) for item in raw.get("evidence") or []]
            if _is_grounded(dim, raw["label"], evidence, turns):
                collected[dim.id].append((raw["label"], evidence))
            else:
                ungrounded += 1
    return {dim.id: _consensus(collected[dim.id]) for dim in rubric.dimensions}, ungrounded


def _identity(payload: dict) -> dict:
    return payload


def _sample_valid(payload: dict, rubric: Rubric) -> bool:
    if not isinstance(payload, dict):
        return False
    for dim in rubric.dimensions:
        raw = payload.get(dim.id)
        if not isinstance(raw, dict):
            return False
        allowed = {label.id for label in dim.labels}
        if raw.get("label") not in allowed:
            return False
    return True


def _is_grounded(dim: DimensionSpec, label: str, evidence: list[Evidence], turns) -> bool:
    spec = next(item for item in dim.labels if item.id == label)
    if spec.no_evidence:
        return True
    by_index = {turn.index: turn.text for turn in turns}
    for item in evidence:
        turn_text = by_index.get(item.turn)
        quote = normalize(item.quote)
        if turn_text is not None and quote and quote in normalize(turn_text):
            return True
    return False


def _consensus(rows: list[tuple[str, list[Evidence]]]) -> DimConsensus:
    labels = [label for label, _evidence in rows]
    if not labels:
        return DimConsensus(label="uncertain", agreement=0.0, n_valid=0, labels=[])
    counts = Counter(labels)
    modal, count = counts.most_common(1)[0]
    chosen = modal if count > len(labels) / 2 else "uncertain"
    evidence: list[Evidence] = []
    if chosen != "uncertain":
        evidence = next(item for label, item in rows if label == chosen)
    return DimConsensus(label=chosen, agreement=count / len(labels), n_valid=len(labels), labels=labels, evidence=evidence)
