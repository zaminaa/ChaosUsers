from chaosusers.packs.loader import load_pack
from chaosusers.panel.artifact import load_artifact, visible_text


def test_planted_flaws_survive_each_reading_filter():
    artifact = load_artifact("examples/artifacts/acme-landing.html")
    pack = load_pack("core-en")
    hero = artifact.sections[0]
    how = next(section for section in artifact.sections if section.title == "How it works")
    account = next(section for section in artifact.sections if section.title == "Create your account")
    tess = visible_text(hero, pack.personas["three-word-answerer"].panel.reading)
    bo = visible_text(account, pack.personas["reminder-blocker"].panel.reading)
    sam = visible_text(how, pack.personas["silent-non-reporter"].panel.reading)
    assert "[BUTTON: Get started]" in tess
    assert "[CHECKBOX pre-ticked:" in bo
    assert "weekly shipment report" in sam
