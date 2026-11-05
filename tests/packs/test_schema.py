from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from chaosusers.packs.schema import BehaviorClass, OperatorSpec, PersonaSpec


def _persona(**overrides) -> dict:
    data = {
        "id": "three-word-answerer",
        "name": "Tess",
        "archetype": "The Three-Word Answerer",
        "behavior_class": "BC03",
        "language": "en",
        "summary": "Answers in one to three words and skips anything long.",
        "trust_in_bot": "normal",
        "voice": {
            "register": "terse, lowercase, no greetings",
            "vocabulary_level": "everyday",
            "typical_phrases": ["yes", "change address"],
            "never": ["greetings or sign-offs"],
            "example_utterance": "change delivery address",
        },
        "modes": ["panel", "gauntlet"],
        "gauntlet": {
            "reading_budget_words": 25,
            "fact_drift": 0.5,
            "patience": {
                "start": 6,
                "costs": {"turn": 0.5, "bot_fallback": 1.5, "bot_repeated": 1.0, "bot_long": 1.0, "bot_asks_known_fact": 2.0},
                "recovery": {"bot_progress": 0.5},
                "frustrated_below": 3,
                "angry_below": 1.5,
                "abandon_at": 0,
                "on_abandon": "leave",
                "abandon_line": None,
            },
            "operators": [{"op": "max_words", "n": 3}, {"op": "lowercase", "p": 0.9}],
            "mind_change": None,
            "scope_push": None,
        },
        "panel": {
            "reading": {"mode": "skim", "words_per_section": 12},
            "attention_focus": ["the main button"],
            "abandon_triggers": ["a wall of text before the first button"],
            "extra_instructions": [],
        },
        "fidelity": {"max_words": 3, "require_script": "any", "forbidden_words": []},
    }
    data.update(overrides)
    return data


def test_example_persona_validates():
    persona = PersonaSpec.model_validate(_persona())
    assert persona.id == "three-word-answerer"
    assert persona.gauntlet is not None
    assert persona.gauntlet.operators[0].n == 3


def test_gauntlet_mode_requires_block():
    raw = _persona()
    raw["modes"] = ["gauntlet"]
    raw["gauntlet"] = None
    with pytest.raises(ValidationError):
        PersonaSpec.model_validate(raw)


def test_non_kebab_id_fails():
    with pytest.raises(ValidationError):
        PersonaSpec.model_validate(_persona(id="Three Words"))


def test_unknown_op_fails():
    with pytest.raises(ValidationError):
        OperatorSpec.model_validate({"op": "sing"})


def test_taxonomy_has_twelve_unique_classes():
    data = yaml.safe_load(Path("packs/taxonomy.yaml").read_text(encoding="utf-8"))
    classes = [BehaviorClass.model_validate(row) for row in data["classes"]]
    assert len(classes) == 12
    assert len({item.id for item in classes}) == 12
