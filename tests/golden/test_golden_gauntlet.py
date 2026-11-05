import json
import os
from pathlib import Path

from chaosusers.config import RunConfig
from chaosusers.gauntlet.runner import run_gauntlet
from tests.golden.normalize import normalize_for_golden

ROOT = Path("tests/golden/expected")
SCRIPT = "tests/golden/scripts/gauntlet.yaml"


def _run(tmp_path: Path) -> tuple[dict, dict]:
    path = run_gauntlet(RunConfig(
        mode="gauntlet", target="demo", scenario="demo", script=Path(SCRIPT),
        seed=33, max_turns=5, repeats=2, concurrency=1, judge_samples=1, out_dir=tmp_path,
    ))
    scores = json.loads((path / "scores.json").read_text(encoding="utf-8"))
    predicted = json.loads((path / "predictions.json").read_text(encoding="utf-8"))
    return normalize_for_golden(scores), normalize_for_golden(predicted)


def test_gauntlet_golden(tmp_path: Path):
    scores, predicted = _run(tmp_path)
    outcomes = [item["outcome"] for item in scores["conversations"]]
    assert "success" in outcomes
    assert outcomes.count("silent_failure") >= 2
    assert "forbidden_action" in outcomes
    assert "abandoned" in outcomes
    assert "stuck" in outcomes
    score_path = ROOT / "gauntlet_scores.json"
    pred_path = ROOT / "gauntlet_predictions.json"
    if os.environ.get("CHAOSUSERS_UPDATE_GOLDEN") == "1" or not score_path.exists():
        ROOT.mkdir(parents=True, exist_ok=True)
        score_path.write_text(json.dumps(scores, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        pred_path.write_text(json.dumps(predicted, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert json.loads(score_path.read_text(encoding="utf-8")) == scores
    assert json.loads(pred_path.read_text(encoding="utf-8")) == predicted
