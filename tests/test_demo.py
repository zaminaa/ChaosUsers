from chaosusers.cli import main


def test_scripted_demos_finish_offline(tmp_path):
    assert main(["demo", "--no-open", "--out", str(tmp_path / "g")]) == 0
    assert main(["demo", "panel", "--no-open", "--out", str(tmp_path / "p")]) == 0
    report = next((tmp_path / "g").rglob("report.html"))
    text = report.read_text(encoding="utf-8")
    assert "SCRIPTED" in text
