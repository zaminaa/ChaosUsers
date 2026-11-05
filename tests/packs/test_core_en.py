import pytest

from chaosusers.packs.loader import load_pack, load_taxonomy

PANEL = [
    "apologetic-novice",
    "mind-changer",
    "privacy-guard",
    "reminder-blocker",
    "romanized-typer",
    "scope-pusher",
    "silent-non-reporter",
    "three-word-answerer",
]
GAUNTLET = [
    "apologetic-novice",
    "caps-escalator",
    "mind-changer",
    "romanized-typer",
    "scope-pusher",
    "three-word-answerer",
]


def test_core_en_modes_and_classes():
    pack = load_pack("core-en")
    taxonomy = load_taxonomy()
    assert [persona.id for persona in pack.for_mode("panel")] == PANEL
    assert [persona.id for persona in pack.for_mode("gauntlet")] == GAUNTLET
    assert all(persona.behavior_class in taxonomy for persona in pack.personas.values())


def test_example_utterances_pass_fidelity():
    pytest.importorskip("chaosusers.engine.fidelity")
    from chaosusers.engine.fidelity import check_fidelity

    pack = load_pack("core-en")
    for persona in pack.personas.values():
        assert check_fidelity(persona.voice.example_utterance, persona) == []
