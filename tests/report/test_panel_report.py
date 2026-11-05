from chaosusers.cli import main
from chaosusers.report.render import load_run, render_panel_report


def test_panel_report_has_friction_map(tmp_path):
    assert main([
        "panel", "examples/artifacts/acme-landing.html",
        "--script", "tests/golden/scripts/panel.yaml",
        "--repeats", "2", "--concurrency", "1", "--out", str(tmp_path),
    ]) == 0
    run_dir = next(tmp_path.iterdir())
    html = render_panel_report(load_run(run_dir))
    assert "would not complete" in html
    assert "<mark>" in html
    assert "Discarded findings" in html
    assert "words read" in html
    assert "Ship smarter, not harder." in html
