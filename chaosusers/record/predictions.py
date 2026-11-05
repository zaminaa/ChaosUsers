import hashlib
import json

from pydantic import BaseModel

from chaosusers.gauntlet.score import GauntletScores
from chaosusers.packs.schema import BehaviorClass, Pack
from chaosusers.record.schema import Prediction, PredictionSet

_FAILING = {"silent_failure", "forbidden_action", "abandoned", "stuck", "incomplete"}
_RANK = {"high": 0, "medium": 1, "low": 2}


def canonical_sha256(obj) -> str:
    payload = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def predictions_from_gauntlet(scores: GauntletScores, scenario, pack: Pack, taxonomy: dict[str, BehaviorClass], run_id: str, subject: str) -> PredictionSet:
    drafts: list[tuple[int, int, Prediction]] = []
    by_persona = {row.persona_id: row for row in scores.persona_rows}
    for step in scores.failure_steps:
        personas = step.personas
        if len(personas) < 2:
            continue
        all_repeats = all(_failed_only_at(scores, persona, step.step) for persona in personas)
        confidence = "high" if len(personas) >= 3 and all_repeats else "medium"
        drafts.append((
            _RANK[confidence], -len(personas),
            Prediction(
                id="", kind="location", step_id=step.step, top_k=3, confidence=confidence,
                claim=f"Step {step.step} will be among the top 3 drop-off points of this flow in production.",
                check_hint=f"Rank your production funnel steps by drop-off; confirmed if {step.step} is in the top 3.",
                support=f"{len(personas)}/{len(by_persona)} personas, {step.conversations}/{len(scores.conversations)} conversations",
                evidence=[item.conversation_id for item in scores.conversations if item.failure_step == step.step and item.outcome in _FAILING],
            ),
        ))
    silent_personas = {item.persona_id for item in scores.conversations if item.outcome == "silent_failure"}
    if silent_personas:
        step = next((item.failure_step for item in scores.conversations if item.outcome == "silent_failure" and item.failure_step), "unknown")
        confidence = "high" if len(silent_personas) >= 2 else "medium"
        drafts.append((
            _RANK[confidence], -len(silent_personas),
            Prediction(
                id="", kind="occurs", failure_type="silent_failure", step_id=step, confidence=confidence,
                claim=f"Some real users will be told their request was completed at step {step} when it was not.",
                check_hint=f"Sample 50 production conversations that reached {step} and compare the bot's success message with backend state.",
                support=f"{len(silent_personas)} personas, {scores.silent_failures} conversations",
                evidence=[item.conversation_id for item in scores.conversations if item.outcome == "silent_failure"],
            ),
        ))
    seen_checks: dict[str, list] = {}
    for item in scores.forbidden:
        seen_checks.setdefault(item["check_id"], []).append(item)
    for rows in seen_checks.values():
        confidence = "high" if len(rows) >= 2 else "medium"
        drafts.append((
            _RANK[confidence], -len(rows),
            Prediction(
                id="", kind="occurs", failure_type="forbidden_action", confidence=confidence,
                claim=f"{rows[0]['description']} will be violated by at least one real user.",
                check_hint="Search production logs/state for the forbidden condition.",
                support=f"{len(rows)} conversations",
                evidence=[row["conversation_id"] for row in rows],
            ),
        ))
    for row in scores.persona_rows:
        steps = {item.failure_step for item in scores.conversations if item.persona_id == row.persona_id and item.outcome in _FAILING}
        if len(row.outcomes) < 1 or any(outcome == "success" for outcome in row.outcomes) or len(steps) != 1:
            continue
        step = next(iter(steps))
        behavior = taxonomy[row.behavior_class]
        drafts.append((
            _RANK["medium"], -1,
            Prediction(
                id="", kind="occurs", failure_type="persona_blocked_at_step", step_id=step,
                behavior_class=row.behavior_class, confidence="medium",
                claim=f"Users who behave like '{row.archetype}' ({behavior.name}) will fail at step {step}.",
                check_hint="Find sessions with: " + "; ".join(behavior.production_signals),
                support=f"{row.persona_id} {len(row.outcomes)}/{len(row.outcomes)} repeats",
                evidence=[item.conversation_id for item in scores.conversations if item.persona_id == row.persona_id],
            ),
        ))
    ordered = [item for _rank, _support, item in sorted(drafts, key=lambda row: (row[0], row[1]))][:10]
    for index, item in enumerate(ordered, start=1):
        item.id = f"P-{index:03d}"
    return PredictionSet(run_id=run_id, created_at="", mode="gauntlet", subject=subject, predictions=ordered)


def predictions_from_panel(scores, artifact, pack, run_id) -> PredictionSet:
    raise NotImplementedError


def _failed_only_at(scores: GauntletScores, persona: str, step: str) -> bool:
    rows = [item for item in scores.conversations if item.persona_id == persona]
    return bool(rows) and all(item.outcome in _FAILING and item.failure_step == step for item in rows)
