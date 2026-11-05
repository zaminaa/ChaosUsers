import xml.etree.ElementTree as ET

from chaosusers.cli import main
from chaosusers.report.render import load_run, render_badge, render_card


def test_card_and_badge(tmp_path):
    assert main([
        "gauntlet", "--target", "demo", "--scenario", "demo", "--script", "tests/golden/scripts/gauntlet.yaml",
        "--seed", "33", "--max-turns", "5", "--repeats", "1", "--concurrency", "1",
        "--judge-samples", "1", "--personas", "three-word-answerer", "--out", str(tmp_path),
    ]) == 0
    run = load_run(next(tmp_path.iterdir()))
    card = render_card(run)
    root = ET.fromstring(card)
    assert root.attrib["width"] == "1200"
    assert root.attrib["height"] == "630"
    assert "UNGRADED" in card or run["scores"]["grade"] in card
    assert "✅" not in card
    assert "pack core-en@" in card
    badge = render_badge(run)
    assert "chaosusers" in badge
    assert (run["scores"]["grade"] or "UNGRADED") in badge
