from chaosusers.engine.state import PatienceState
from chaosusers.packs.schema import PatienceSpec


def _caps() -> PatienceState:
    return PatienceState(
        spec=PatienceSpec(
            start=5,
            costs={"turn": 1.0},
            recovery={"bot_progress": 2.0},
            frustrated_below=4.5,
            angry_below=3.5,
            abandon_at=0,
        ),
        value=5,
    )


def test_caps_escalator_mood_then_abandon():
    state = _caps()
    state.apply(["turn"])
    assert state.value == 4
    assert state.mood == "frustrated"
    state.apply(["turn"])
    assert state.value == 3
    assert state.mood == "angry"
    state.apply(["turn"])
    state.apply(["turn"])
    state.apply(["turn"])
    assert state.value == 0
    assert state.abandoned is True


def test_recovery_is_capped_at_start():
    state = _caps()
    state.apply(["bot_progress"])
    assert state.value == 5
    assert state.mood == "calm"
