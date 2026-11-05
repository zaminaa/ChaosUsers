from chaosusers.gauntlet.checks import evaluate_checks
from chaosusers.gauntlet.driver import Transcript, Turn
from chaosusers.gauntlet.scenario import CheckSpec, MindChange, Scenario, effective_match_tokens


def _scenario(checks: list[CheckSpec]) -> Scenario:
    base = __import__("chaosusers.gauntlet.scenario", fromlist=["load_scenario"]).load_scenario("demo")
    return base.model_copy(update={"checks": checks})


def _transcript(state, changes=None, bot="hello") -> Transcript:
    return Transcript(
        conversation_id="t--r0",
        persona_id="t",
        scenario_id="acme-change-address",
        repeat=0,
        seed=1,
        remembered_facts={},
        applied_mind_changes=changes or [],
        turns=[Turn(index=1, role="bot", text=bot)],
        end_reason="persona_done",
        final_state=state,
    )


def test_each_check_type():
    scenario = _scenario(
        [
            CheckSpec(id="eq", kind="success", type="state_equals", path="orders.A1001.status", value="processing", description="eq"),
            CheckSpec(id="tok", kind="success", type="state_tokens", path="orders.A1001.address", fact="new_address", description="tok"),
            CheckSpec(id="abs", kind="success", type="state_absent", path="missing", description="abs"),
            CheckSpec(id="empty", kind="forbidden", type="state_empty", path="refunds", description="empty"),
            CheckSpec(id="hit", kind="quality", type="bot_matches", pattern="Done", description="hit"),
            CheckSpec(id="never", kind="forbidden", type="bot_never_matches", pattern="secret", description="never"),
            CheckSpec(id="turns", kind="quality", type="max_user_turns", n=2, description="turns"),
        ]
    )
    state = {"orders": {"A1001": {"status": "processing", "address": "48 Elm Road"}}, "refunds": {}}
    results = {item.check_id: item.passed for item in evaluate_checks(scenario, _transcript(state, bot="Done"))}
    assert results == {"eq": True, "tok": True, "abs": True, "empty": True, "hit": True, "never": True, "turns": True}

    failed_state = {"orders": {"A1001": {"status": "nope", "address": "nowhere"}}, "refunds": {"A1002": {}}, "secret": 1}
    failed = {item.check_id: item.passed for item in evaluate_checks(scenario, _transcript(failed_state, bot="secret"))}
    assert failed["eq"] is False
    assert failed["tok"] is False
    assert failed["abs"] is True
    assert failed["empty"] is False
    assert failed["hit"] is False
    assert failed["never"] is False

    missing = {item.check_id: item.passed for item in evaluate_checks(scenario, _transcript(None))}
    assert missing["eq"] is None
    assert missing["tok"] is None
    assert missing["empty"] is None
    assert missing["hit"] is False


def test_state_tokens_follow_mind_change():
    scenario = _scenario(
        [CheckSpec(id="tok", kind="success", type="state_tokens", path="orders.A1001.address", fact="new_address", description="tok")]
    )
    change = MindChange(fact="new_address", to="harbor", match_tokens=["200", "harbor"])
    state = {"orders": {"A1001": {"address": "200 Harbor Street"}}}
    transcript = _transcript(state, changes=[change])
    assert effective_match_tokens(scenario, "new_address", transcript.applied_mind_changes) == ["200", "harbor"]
    assert evaluate_checks(scenario, transcript)[0].passed is True
    assert evaluate_checks(scenario, _transcript(state))[0].passed is False
