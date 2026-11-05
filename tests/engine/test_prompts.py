from types import SimpleNamespace

import pytest
from jinja2 import UndefinedError

from chaosusers.engine.persona import build_instance, language_examples, language_instruction
from chaosusers.engine.prompts import prompt_hashes, render
from chaosusers.gauntlet.scenario import FactSpec
from chaosusers.packs.loader import load_pack


def test_gauntlet_prompt_includes_empty_transcript_and_facts():
    pack = load_pack("core-en")
    spec = pack.personas["three-word-answerer"]
    scenario = SimpleNamespace(
        context="You moved house.",
        task="Change the delivery address.",
        facts={
            "order_id": FactSpec(value="#A1001", variants=["order 1001"], match_tokens=["A1001"]),
        },
    )
    inst = build_instance(spec.model_copy(update={"gauntlet": spec.gauntlet.model_copy(update={"fact_drift": 0})}), 1, scenario)
    system, user = render(
        "persona_gauntlet_v1",
        p=spec,
        language_instruction=language_instruction(pack, spec.language),
        language_examples=language_examples(pack, spec.language),
        scenario=scenario,
        facts=inst.remembered_facts,
        mood="calm",
        directives=[],
        turns=[],
    )
    rendered = f"{system}\n{user}"
    assert "(nothing yet" in rendered
    assert "#A1001" in rendered


def test_unknown_variable_raises():
    with pytest.raises(UndefinedError):
        render("persona_gauntlet_v1", p=load_pack("core-en").personas["three-word-answerer"])


def test_prompt_hashes_cover_three_files():
    assert len(prompt_hashes()) == 3
