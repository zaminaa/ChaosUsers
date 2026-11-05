import json
import re
from pathlib import Path

from chaosusers.cli import main

_IDS = re.compile(
    "reminder-blocker|silent-non-reporter|three-word-answerer|apologetic-novice|mind-changer|"
    "romanized-typer|caps-escalator|privacy-guard|scope-pusher|BC0[0-9]|BC1[0-9]"
)
_EMAIL = re.compile(r"\S+@\S+\.\w+")
_URL = re.compile(r"https?://")
_PHONE = re.compile(r"\+?\d[\d\s-]{8,}\d")


def test_budget_turn_cap_and_static_scans(tmp_path, monkeypatch):
    assert main([
        "gauntlet", "--target", "demo", "--scenario", "demo", "--script", "tests/golden/scripts/gauntlet.yaml",
        "--personas", "three-word-answerer", "--repeats", "1", "--max-turns", "3", "--max-usd", "0.0001",
        "--out", str(tmp_path),
    ]) == 0
    run = next(path for path in tmp_path.iterdir() if path.is_dir())
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["cost"]["usd"] <= 0.001
    assert manifest["status"] == "budget_exhausted"
    assert main(["report", str(run)]) == 0
    assert (run / "report.html").is_file()

    turned = tmp_path / "turns"
    assert main([
        "gauntlet", "--target", "demo", "--scenario", "demo", "--script", "tests/golden/scripts/gauntlet.yaml",
        "--personas", "mind-changer", "--repeats", "1", "--max-turns", "3", "--max-usd", "1",
        "--out", str(turned),
    ]) == 0
    transcript = (next(turned.iterdir()) / "transcripts.jsonl").read_text(encoding="utf-8")
    for line in transcript.splitlines():
        users = [turn for turn in json.loads(line)["turns"] if turn["role"] == "user"]
        assert len(users) <= 3

    bad = [str(path) for path in Path("chaosusers").rglob("*.py") if _IDS.search(path.read_text(encoding="utf-8"))]
    assert bad == []
    assert not any("while True" in path.read_text(encoding="utf-8") for path in Path("chaosusers").rglob("*.py"))
    for path in Path("packs").rglob("*"):
        if not path.is_file() or path.suffix not in {".yaml", ".yml", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert _EMAIL.search(text) is None
        assert _URL.search(text) is None
        assert _PHONE.search(text) is None
    denylist = tmp_path / "deny.txt"
    denylist.write_text("secret-employer\n", encoding="utf-8")
    monkeypatch.setenv("CHAOSUSERS_PRIVACY_DENYLIST", str(denylist))
    assert "secret-employer" not in Path("packs/taxonomy.yaml").read_text(encoding="utf-8")
