import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from chaosusers.record.predictions import canonical_sha256
from chaosusers.record.schema import Observed, PredictionSet, Verification, VerificationResult


def verify_run(run_dir: Path, observed_path: Path) -> Verification:
    root = Path(run_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    predicted = PredictionSet.model_validate(json.loads((root / "predictions.json").read_text(encoding="utf-8")))
    raw = yaml.safe_load(Path(observed_path).read_text(encoding="utf-8"))
    if "observed_at" in raw and not isinstance(raw["observed_at"], str):
        raw["observed_at"] = str(raw["observed_at"])
    observed = Observed.model_validate(raw)
    intact = canonical_sha256(predicted) == manifest["predictions_sha256"]
    results = []
    for item in predicted.predictions:
        if item.kind == "location":
            ranking = observed.dropoff_ranking
            top = ranking[: item.top_k or 3]
            if item.step_id in top:
                status, note = "confirmed", "in the top drop-off steps"
            elif item.step_id in ranking:
                status, note = "refuted", "ranked, but outside the top k"
            else:
                status, note = "untested", "step was not in the observed ranking"
        elif item.id in observed.occurrences:
            status = "confirmed" if observed.occurrences[item.id] else "refuted"
            note = "observed" if observed.occurrences[item.id] else "not observed"
        else:
            status, note = "untested", "no observation for this id"
        results.append(VerificationResult(id=item.id, status=status, note=note))
    confirmed = sum(item.status == "confirmed" for item in results)
    refuted = sum(item.status == "refuted" for item in results)
    untested = sum(item.status == "untested" for item in results)
    precision = (confirmed / (confirmed + refuted)) if (confirmed + refuted) else None
    return Verification(
        run_id=manifest["run_id"], verified_at=datetime.now(UTC).isoformat(), receipt_intact=intact,
        results=results, confirmed=confirmed, refuted=refuted, untested=untested, precision=precision,
    )
