import json
from pathlib import Path

from chaosusers.cli import main

SCRIPT = "tests/golden/scripts/gauntlet.yaml"


def test_scripted_run_writes_files(tmp_path: Path):
    code = main([
        "gauntlet", "--target", "demo", "--scenario", "demo", "--script", SCRIPT,
        "--seed", "33", "--max-turns", "5", "--repeats", "2", "--concurrency", "1",
        "--judge-samples", "1", "--out", str(tmp_path),
    ])
    assert code == 0
    run = next(tmp_path.iterdir())
    for name in ("manifest.json", "scores.json", "predictions.json", "transcripts.jsonl"):
        assert (run / name).is_file()
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["prompts"]) == 3
    assert manifest["predictions_sha256"]
    scores = json.loads((run / "scores.json").read_text(encoding="utf-8"))
    outcomes = [item["outcome"] for item in scores["conversations"]]
    assert "success" in outcomes
    assert outcomes.count("silent_failure") >= 2
    assert "forbidden_action" in outcomes
    assert "abandoned" in outcomes
    assert "stuck" in outcomes


def test_dry_run_makes_no_calls(capsys):
    assert main(["gauntlet", "--target", "demo", "--scenario", "demo", "--script", SCRIPT, "--dry-run"]) == 0
    assert "Worst-case cost:" in capsys.readouterr().out


def test_tiny_cap_exhausts_budget(tmp_path: Path):
    code = main([
        "gauntlet", "--target", "demo", "--scenario", "demo", "--script", SCRIPT,
        "--personas", "three-word-answerer", "--repeats", "1", "--max-turns", "2",
        "--max-usd", "0.0001", "--out", str(tmp_path),
    ])
    assert code == 0
    run = next(tmp_path.iterdir())
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "budget_exhausted"
    assert manifest["cost"]["usd"] <= 0.0001


def test_fail_under_a_exits_1(tmp_path: Path):
    code = main([
        "gauntlet", "--target", "demo", "--scenario", "demo", "--script", SCRIPT,
        "--seed", "33", "--max-turns", "5", "--repeats", "2", "--concurrency", "1",
        "--judge-samples", "1", "--fail-under", "A", "--out", str(tmp_path),
    ])
    assert code == 1
