from chaosusers.engine.fidelity import check_fidelity
from chaosusers.packs.schema import FidelitySpec, PersonaSpec, VoiceSpec


def _spec(**fidelity) -> PersonaSpec:
    return PersonaSpec(
        id="sample-user",
        name="Ada",
        archetype="Sample",
        behavior_class="BC03",
        language="en",
        summary="A sample.",
        voice=VoiceSpec(
            register="plain",
            vocabulary_level="everyday",
            typical_phrases=["yes"],
            example_utterance="yes",
        ),
        modes=["gauntlet"],
        gauntlet={
            "reading_budget_words": 20,
            "fact_drift": 0,
            "patience": {"start": 5, "frustrated_below": 2, "angry_below": 1},
        },
        fidelity=FidelitySpec(**fidelity),
    )


def test_flags_persian_when_latin_required():
    assert check_fidelity("سلام", _spec(require_script="Latin")) == ["script:expected Latin"]


def test_forbidden_word_is_whole_word():
    spec = _spec(forbidden_words=["SSO"])
    assert check_fidelity("use SSO please", spec) == ["forbidden_word:SSO"]
    assert check_fidelity("lasso", spec) == []
