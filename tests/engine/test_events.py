from chaosusers.engine.events import detect_events
from chaosusers.gauntlet.scenario import FactSpec


def _facts() -> dict[str, FactSpec]:
    return {
        "order_id": FactSpec(
            value="#A1001",
            variants=["order 1001"],
            match_tokens=["A1001"],
            asked_by="order number",
        )
    }


def test_repeated_long_known_and_progress():
    repeated = detect_events(
        "Please reply YES or NO.",
        ["Please reply YES or NO."],
        ["order 1001"],
        [],
        _facts(),
        step_index=1,
        max_step_index_so_far=0,
        reading_budget_words=3,
    )
    assert "bot_repeated" in repeated
    assert "bot_long" in repeated
    assert "bot_asks_known_fact" not in repeated
    assert "bot_progress" in repeated

    asked = detect_events(
        "What is your order number?",
        [],
        ["I said order 1001"],
        [],
        _facts(),
        step_index=1,
        max_step_index_so_far=1,
        reading_budget_words=20,
    )
    assert "bot_asks_known_fact" in asked
    assert "bot_progress" not in asked

    not_yet = detect_events(
        "What is your order number?",
        [],
        ["hello"],
        [],
        _facts(),
        step_index=None,
        max_step_index_so_far=-1,
        reading_budget_words=20,
    )
    assert not_yet == ["turn"]
