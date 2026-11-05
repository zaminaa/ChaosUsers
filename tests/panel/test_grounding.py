from chaosusers.packs.schema import ReadingSpec
from chaosusers.panel.artifact import load_artifact, visible_text
from chaosusers.panel.grounding import ground_findings
from chaosusers.panel.models import Finding, PanelOutput, PanelResponse


def test_skimmed_quote_is_not_visible_and_whitespace_is_ok():
    artifact = load_artifact("examples/artifacts/acme-landing.html")
    hero = artifact.sections[0]
    visible = {hero.id: visible_text(hero, ReadingSpec(mode="skim", words_per_section=4))}
    hidden = PanelResponse(
        persona_id="tess", repeat=0, valid=True, words_read=4,
        output=PanelOutput(
            verdict="would_abandon", abandon_at="S1", first_impression="Too much.",
            findings=[Finding(section_id="S1", type="confused", artifact_quote="returns orchestration in", in_character_quote="nope", explanation="Hidden by the skim.", severity=2)],
        ),
    )
    ground_findings(hidden, artifact, visible)
    assert hidden.output.findings[0].ungrounded_reason == "not_in_visible_text"
    shown = hidden.model_copy(deep=True)
    shown.output.findings[0].artifact_quote = "  Acme   Parcels for Business "
    ground_findings(shown, artifact, {hero.id: hero.text})
    assert shown.output.findings[0].grounded is True
