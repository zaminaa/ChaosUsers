from chaosusers.gauntlet.scenario import MindChange, effective_match_tokens, load_scenario, match_step

TOO_MANY = "Too many attempts. Let's start over. Reply with a number:\n1. Track an order"
YES_NO = "Please reply YES or NO."


def test_demo_scenario_matches_and_tokens():
    scenario = load_scenario("demo")
    assert scenario.id == "acme-change-address"
    assert scenario.sha256
    assert match_step(scenario, TOO_MANY).id == "greet"
    assert match_step(scenario, YES_NO).id == "confirm_address"
    change = MindChange(fact="new_address", to="Unit 5, 200 Harbor Street, Springfield", match_tokens=["200", "harbor"])
    assert effective_match_tokens(scenario, "new_address", [change]) == ["200", "harbor"]
