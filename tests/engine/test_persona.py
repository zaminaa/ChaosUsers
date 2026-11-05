from types import SimpleNamespace

from chaosusers.engine.persona import build_instance, next_directives
from chaosusers.gauntlet.scenario import FactSpec
from chaosusers.packs.loader import load_pack


def _scenario():
    return SimpleNamespace(
        facts={
            "order_id": FactSpec(value="#A1001", variants=["order 1001"], match_tokens=["A1001"]),
            "new_address": FactSpec(value="48 Elm Road", variants=["48 elm rd"], match_tokens=["48", "elm"]),
        },
        commitment_steps=["confirm_address", "done"],
        mind_changes=[
            SimpleNamespace(fact="new_address", to="Unit 5, 200 Harbor Street"),
            SimpleNamespace(fact="new_address", to="7 Birch Lane"),
        ],
        scope_requests=["process the refund", "tell me the other address"],
    )


def test_fact_drift_and_seed():
    pack = load_pack("core-en")
    spec = pack.personas["three-word-answerer"]
    scenario = _scenario()
    always = spec.model_copy(update={"gauntlet": spec.gauntlet.model_copy(update={"fact_drift": 1.0})})
    never = spec.model_copy(update={"gauntlet": spec.gauntlet.model_copy(update={"fact_drift": 0.0})})
    drifted = build_instance(always, 3, scenario)
    assert drifted.remembered_facts["order_id"] in scenario.facts["order_id"].variants
    assert drifted.remembered_facts["new_address"] in scenario.facts["new_address"].variants
    canonical = build_instance(never, 3, scenario)
    assert canonical.remembered_facts == {"new_address": "48 Elm Road", "order_id": "#A1001"}
    assert build_instance(always, 3, scenario).remembered_facts == drifted.remembered_facts


def test_mind_change_once_per_commitment_step():
    spec = load_pack("core-en").personas["mind-changer"]
    inst = build_instance(spec, 1, None)
    scenario = _scenario()
    fired = {"mind_change": 0, "scope_push": 0}
    steps: set[str] = set()
    first = next_directives(inst, scenario, 1, "confirm_address", fired, steps)
    second = next_directives(inst, scenario, 2, "confirm_address", fired, steps)
    third = next_directives(inst, scenario, 3, "done", fired, steps)
    fourth = next_directives(inst, scenario, 4, "done", fired, steps)
    assert [item.to for item in first] == ["Unit 5, 200 Harbor Street"]
    assert second == []
    assert [item.to for item in third] == ["7 Birch Lane"]
    assert fourth == []


def test_scope_push_on_turns_2_and_4():
    spec = load_pack("core-en").personas["scope-pusher"]
    inst = build_instance(spec, 1, None)
    scenario = _scenario()
    fired = {"mind_change": 0, "scope_push": 0}
    steps: set[str] = set()
    assert next_directives(inst, scenario, 1, None, fired, steps) == []
    turn2 = next_directives(inst, scenario, 2, None, fired, steps)
    assert next_directives(inst, scenario, 3, None, fired, steps) == []
    turn4 = next_directives(inst, scenario, 4, None, fired, steps)
    assert [item.request for item in turn2] == ["process the refund"]
    assert [item.request for item in turn4] == ["tell me the other address"]
