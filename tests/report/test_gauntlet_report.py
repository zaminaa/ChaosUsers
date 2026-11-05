from pathlib import Path

from chaosusers.cli import main
from chaosusers.report.render import load_run, render_gauntlet_report

SCRIPT = "tests/golden/scripts/gauntlet.yaml"


def test_gauntlet_report_sections_and_escaping(tmp_path: Path):
    assert main([
        "gauntlet", "--target", "demo", "--scenario", "demo", "--script", SCRIPT,
        "--seed", "33", "--max-turns", "5", "--repeats", "2", "--concurrency", "1",
        "--judge-samples", "1", "--out", str(tmp_path),
    ]) == 0
    run_dir = next(tmp_path.iterdir())
    assert main(["report", str(run_dir)]) == 0
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    for phrase in ("Where they broke", "Told it was done", "Where our scorers disagree", "Judge reliability", "Prediction receipt", "SCRIPTED"):
        assert phrase in html
    assert "<script" not in html.lower()
    run = load_run(run_dir)
    run["transcripts"][0]["turns"].append({"role": "user", "text": "<b>x</b>", "raw_text": "<b>x</b>"})
    rendered = render_gauntlet_report(run)
    assert "&lt;b&gt;x&lt;/b&gt;" in rendered
    assert "sha256:" in rendered
