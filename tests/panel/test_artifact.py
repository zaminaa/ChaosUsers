from pathlib import Path

from chaosusers.packs.schema import ReadingSpec
from chaosusers.panel.artifact import load_artifact, visible_text

PAGE = "examples/artifacts/acme-landing.html"


def test_landing_sections_and_markers():
    artifact = load_artifact(PAGE)
    titles = [section.title for section in artifact.sections]
    assert titles == [
        "Ship smarter, not harder.",
        "How it works",
        "Pricing",
        "Create your account",
        "Built for growing teams",
        "Footer",
    ]
    account = next(section for section in artifact.sections if section.title == "Create your account")
    assert "[CHECKBOX pre-ticked: Send me WhatsApp reminders and partner offers]" in account.text
    assert "[FIELD: Mobile phone number (required — used for delivery alerts)]" in account.text


def test_skim_keeps_markers():
    artifact = load_artifact(PAGE)
    hero = artifact.sections[0]
    visible = visible_text(hero, ReadingSpec(mode="skim", words_per_section=12))
    assert visible.count("[BUTTON:") == hero.text.count("[BUTTON:")
    assert "…" in visible


def test_markdown_numbered_steps():
    artifact = load_artifact("examples/artifacts/acme-onboarding.md")
    assert len(artifact.sections) == 6


def test_botscript_sections():
    artifact = load_artifact("examples/artifacts/acme-botscript.yaml")
    assert [section.title for section in artifact.sections] == ["welcome", "order", "confirm"]
    assert "[BUTTON: YES]" in artifact.sections[-1].text


def test_url_uses_injected_fetch():
    html = Path(PAGE).read_text(encoding="utf-8")
    artifact = load_artifact("https://acme.example/landing", fetch=lambda _url: html)
    assert artifact.kind == "page"
    assert artifact.sections[0].title == "Ship smarter, not harder."
