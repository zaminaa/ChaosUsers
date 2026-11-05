import random

from chaosusers.engine.operators import apply_operators
from chaosusers.packs.schema import Lexicon, OperatorSpec


def _lexicon() -> Lexicon:
    return Lexicon(language="en", apology_phrases=["sorry", "sorry if this is wrong"])


def _ops(*rows: dict) -> list[OperatorSpec]:
    return [OperatorSpec.model_validate(row) for row in rows]


def test_max_words():
    text = apply_operators(
        "I want to change address",
        _ops({"op": "max_words", "n": 3}),
        "calm",
        random.Random(1),
        _lexicon(),
    )
    assert text == "I want to"


def test_uppercase_only_when_angry():
    ops = _ops({"op": "uppercase", "when_mood": ["angry"]})
    assert apply_operators("Hello there", ops, "calm", random.Random(1), _lexicon()) == "Hello there"
    assert apply_operators("Hello there", ops, "angry", random.Random(1), _lexicon()) == "HELLO THERE"


def test_typos_are_seeded_and_spare_ids():
    ops = _ops({"op": "typos", "rate": 1.0})
    first = apply_operators("please change #A1001 and 1001 today", ops, "calm", random.Random(4), _lexicon())
    second = apply_operators("please change #A1001 and 1001 today", ops, "calm", random.Random(4), _lexicon())
    assert first == second
    assert "#A1001" in first
    assert "1001" in first.split()
    assert "and" in first.split()


def test_apology_prefix_uses_lexicon():
    text = apply_operators("hello", _ops({"op": "apology_prefix"}), "calm", random.Random(0), _lexicon())
    assert text.startswith("sorry")
    assert text.endswith("hello")


def test_strip_punctuation_keeps_hash():
    text = apply_operators("Wait, #A1001!", _ops({"op": "strip_punctuation"}), "calm", random.Random(1), _lexicon())
    assert text == "Wait #A1001"


def test_same_seed_is_stable():
    ops = _ops({"op": "lowercase", "p": 0.5}, {"op": "typos", "rate": 0.4}, {"op": "exclaim", "p": 0.5})
    outputs = {
        apply_operators("Please change the address", ops, "frustrated", random.Random(9), _lexicon())
        for _ in range(100)
    }
    assert len(outputs) == 1
