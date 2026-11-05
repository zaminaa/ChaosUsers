from chaosusers.cli import main


def test_scripted_panel_run(tmp_path):
    code = main([
        "panel", "examples/artifacts/acme-landing.html",
        "--script", "tests/golden/scripts/panel.yaml",
        "--repeats", "2", "--concurrency", "1", "--out", str(tmp_path),
    ])
    assert code == 0
    run = next(tmp_path.iterdir())
    assert (run / "scores.json").is_file()
    assert (run / "predictions.json").is_file()
    assert (run / "artifact.json").is_file()
