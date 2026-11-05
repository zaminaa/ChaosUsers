import random
import re

from chaosusers.packs.schema import Lexicon, Mood, OperatorSpec

_PUNCT = str.maketrans("", "", ".,;:!?")


def apply_operators(
    text: str,
    ops: list[OperatorSpec],
    mood: Mood,
    rng: random.Random,
    lexicon: Lexicon,
) -> str:
    """Mood-skipped operators do not draw from rng. Every other operator draws once for p."""
    for op in ops:
        if mood not in op.when_mood:
            continue
        if rng.random() >= op.p:
            continue
        text = _apply(text, op, rng, lexicon)
    return text


def _apply(text: str, op: OperatorSpec, rng: random.Random, lexicon: Lexicon) -> str:
    if op.op == "max_words":
        return " ".join(text.split()[: op.n or 0])
    if op.op == "lowercase":
        return text.lower()
    if op.op == "uppercase":
        return text.upper()
    if op.op == "strip_punctuation":
        return text.translate(_PUNCT)
    if op.op == "exclaim":
        return text if text.endswith("!") else f"{text}!!"
    if op.op == "apology_prefix":
        phrase = rng.choice(lexicon.apology_phrases)
        return f"{phrase} {text}"
    if op.op == "typos":
        return _typos(text, op.rate if op.rate is not None else 0.0, rng)
    return text


def _typos(text: str, rate: float, rng: random.Random) -> str:
    parts = re.split(r"(\s+)", text)
    changed = []
    for part in parts:
        if part.isalpha() and len(part) >= 4 and rng.random() < rate:
            changed.append(_mutate(part, rng))
        else:
            changed.append(part)
    return "".join(changed)


def _mutate(word: str, rng: random.Random) -> str:
    kind = rng.randrange(3)
    inner = list(range(1, len(word) - 1))
    if kind == 0 and len(inner) >= 2:
        index = rng.choice(inner[:-1])
        chars = list(word)
        chars[index], chars[index + 1] = chars[index + 1], chars[index]
        return "".join(chars)
    if kind == 1 and inner:
        index = rng.choice(inner)
        return word[:index] + word[index + 1 :]
    index = rng.randrange(len(word))
    return word[:index] + word[index] + word[index:]
