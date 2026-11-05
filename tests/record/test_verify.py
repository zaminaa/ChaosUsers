import json

from chaosusers.record.predictions import canonical_sha256
from chaosusers.record.schema import Prediction, PredictionSet
from chaosusers.record.verify import verify_run


def _write(tmp_path, predicted: PredictionSet, sha: str | None = None):
    run = tmp_path / "run"
    run.mkdir()
    (run / "predictions.json").write_text(predicted.model_dump_json(indent=2), encoding="utf-8")
    (run / "manifest.json").write_text(json.dumps({
        "run_id": "run-1", "predictions_sha256": sha or canonical_sha256(predicted),
    }), encoding="utf-8")
    (run / "scores.json").write_text("{}", encoding="utf-8")
    observed = tmp_path / "observed.yaml"
    observed.write_text(
        "run_id: other\nobserved_at: 2026-12-01\nsource: test\n"
        "dropoff_ranking: [confirm_address, ask_order]\noccurrences:\n  P-002: true\n",
        encoding="utf-8",
    )
    return run, observed


def test_location_and_occurs_and_tamper(tmp_path):
    predicted = PredictionSet(run_id="run-1", created_at="t", mode="gauntlet", subject="bot", predictions=[
        Prediction(id="P-001", kind="location", claim="step", step_id="confirm_address", top_k=1, check_hint="h", support="s", confidence="high", evidence=[]),
        Prediction(id="P-002", kind="occurs", claim="happens", failure_type="silent_failure", check_hint="h", support="s", confidence="medium", evidence=[]),
        Prediction(id="P-004", kind="location", claim="later", step_id="ask_order", top_k=1, check_hint="h", support="s", confidence="medium", evidence=[]),
    ])
    run, observed = _write(tmp_path, predicted)
    result = verify_run(run, observed)
    assert [item.status for item in result.results] == ["confirmed", "confirmed", "refuted"]
    assert result.receipt_intact is True
    assert result.precision == 2 / 3
    tampered = predicted.model_copy(deep=True)
    tampered.predictions[0].claim = "changed"
    (run / "predictions.json").write_text(tampered.model_dump_json(indent=2), encoding="utf-8")
    broken = verify_run(run, observed)
    assert broken.receipt_intact is False


def test_precision_is_none_when_nothing_was_tested(tmp_path):
    predicted = PredictionSet(run_id="run-1", created_at="t", mode="gauntlet", subject="bot", predictions=[
        Prediction(id="P-009", kind="occurs", claim="unknown", check_hint="h", support="s", confidence="low", evidence=[]),
    ])
    run, observed = _write(tmp_path, predicted)
    assert verify_run(run, observed).precision is None
