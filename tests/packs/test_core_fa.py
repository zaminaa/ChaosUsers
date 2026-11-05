from chaosusers.engine.fidelity import check_fidelity
from chaosusers.packs.loader import load_pack


def test_core_fa_overlay():
    pack = load_pack("core-fa")
    pat = pack.personas["apologetic-novice"]
    assert pat.language == "fa"
    assert pat.gauntlet is not None
    assert pat.gauntlet.patience.start == 10
    navid = pack.personas["romanized-typer"]
    assert navid.language == "fa-Latn"
    for persona in pack.personas.values():
        if persona.language == "fa":
            assert check_fidelity(persona.voice.example_utterance, persona) == []
    assert len(pack.for_mode("panel")) == 8
    assert len(pack.for_mode("gauntlet")) == 6
