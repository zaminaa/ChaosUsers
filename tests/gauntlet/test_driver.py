import json

from chaosusers.engine.persona import build_instance
from chaosusers.gauntlet.driver import run_conversation
from chaosusers.gauntlet.scenario import load_scenario
from chaosusers.gauntlet.targets import PythonTarget, TargetError
from chaosusers.llm.budget import Budget
from chaosusers.llm.client import LLMClient
from chaosusers.llm.testing import ScriptedProvider
from chaosusers.packs.loader import load_pack


def _client(lines: list[str], budget: Budget | None = None) -> LLMClient:
    return LLMClient(ScriptedProvider({"default": lines}), budget or Budget(1, 100_000, 0, 0), None)


def _line(message: str, status: str = "continue") -> str:
    return json.dumps({"message": message, "status": status})


def test_scripted_success_updates_state():
    pack = load_pack("core-en")
    spec = pack.personas["three-word-answerer"]
    spec = spec.model_copy(update={"gauntlet": spec.gauntlet.model_copy(update={"operators": [spec.gauntlet.operators[0]]})})
    inst = build_instance(spec, 1, None)
    target = PythonTarget("AcmeBot (demo)", __import__("chaosusers.demo.acmebot", fromlist=["AcmeBot"]).AcmeBot())
    transcript = run_conversation(
        inst, load_scenario("demo"), target, _client([
            _line("2"), _line("#A1001"), _line("48 elm rd"), _line("yes"), _line("ok", "done"),
        ]),
        pack, "gpt-4.1-mini", 8, 0, "run",
    )
    assert transcript.end_reason == "persona_done"
    assert transcript.final_state["orders"]["A1001"]["address"] == "48 elm rd"


def test_turn_cap_counts_user_turns():
    pack = load_pack("core-en")
    spec = pack.personas["three-word-answerer"].model_copy(
        update={"gauntlet": pack.personas["three-word-answerer"].gauntlet.model_copy(update={"operators": []})}
    )
    transcript = run_conversation(
        build_instance(spec, 1, None), load_scenario("demo"),
        PythonTarget("bot", __import__("chaosusers.demo.acmebot", fromlist=["AcmeBot"]).AcmeBot()),
        _client([_line("hello??")]), pack, "m", 3, 0, "run",
    )
    assert transcript.end_reason == "turn_cap"
    assert sum(turn.role == "user" for turn in transcript.turns) == 3


def test_caps_uppercase_on_third_message():
    pack = load_pack("core-en")
    spec = pack.personas["caps-escalator"]
    transcript = run_conversation(
        build_instance(spec, 1, None), load_scenario("demo"),
        PythonTarget("bot", __import__("chaosusers.demo.acmebot", fromlist=["AcmeBot"]).AcmeBot()),
        _client([_line("hello")]), pack, "m", 3, 0, "run",
    )
    user_turns = [turn.text for turn in transcript.turns if turn.role == "user"]
    assert user_turns[2].isupper()


def test_go_silent_does_not_send():
    pack = load_pack("core-en")
    base = pack.personas["apologetic-novice"]
    patience = base.gauntlet.patience.model_copy(update={"start": 1, "costs": {"turn": 1}, "on_abandon": "go_silent", "abandon_at": 0})
    spec = base.model_copy(update={"gauntlet": base.gauntlet.model_copy(update={"patience": patience, "operators": []})})
    sent = []

    class Bot:
        def handle(self, session_id, message):
            sent.append(message)
            return {"reply": "...", "state_name": "menu"}

        def state(self, session_id):
            return {}

    transcript = run_conversation(
        build_instance(spec, 1, None), load_scenario("demo"), PythonTarget("bot", Bot()),
        _client([_line("hello")]), pack, "m", 4, 0, "run",
    )
    assert transcript.end_reason == "abandoned"
    assert any(turn.role == "system_marker" for turn in transcript.turns)
    assert sent == ["hello"]


def test_mind_change_recorded_at_confirm():
    pack = load_pack("core-en")
    spec = pack.personas["mind-changer"].model_copy(
        update={"gauntlet": pack.personas["mind-changer"].gauntlet.model_copy(update={"operators": []})}
    )
    transcript = run_conversation(
        build_instance(spec, 1, None), load_scenario("demo"),
        PythonTarget("bot", __import__("chaosusers.demo.acmebot", fromlist=["AcmeBot"]).AcmeBot()),
        _client([_line("2"), _line("#A1001"), _line("48 Elm Road, Springfield"), _line("wait actually office")]),
        pack, "m", 6, 0, "run",
    )
    assert transcript.applied_mind_changes
    assert transcript.applied_mind_changes[0].to.startswith("Unit 5")


def test_budget_exhausted_still_returns_state():
    pack = load_pack("core-en")
    spec = pack.personas["three-word-answerer"]
    budget = Budget(0.0001, 10, 0.40, 1.60)
    transcript = run_conversation(
        build_instance(spec, 1, None), load_scenario("demo"),
        PythonTarget("bot", __import__("chaosusers.demo.acmebot", fromlist=["AcmeBot"]).AcmeBot()),
        _client([_line("2")], budget), pack, "gpt-4.1-mini", 4, 0, "run",
    )
    assert transcript.end_reason == "budget_exhausted"
    assert transcript.final_state is not None


def test_target_error_is_recorded():
    pack = load_pack("core-en")
    spec = pack.personas["three-word-answerer"].model_copy(
        update={"gauntlet": pack.personas["three-word-answerer"].gauntlet.model_copy(update={"operators": []})}
    )

    class Bot:
        def handle(self, session_id, message):
            raise TargetError("down")

        def state(self, session_id):
            return {"ok": True}

    transcript = run_conversation(
        build_instance(spec, 1, None), load_scenario("demo"), PythonTarget("bot", Bot()),
        _client([_line("2")]), pack, "m", 2, 0, "run",
    )
    assert transcript.end_reason == "target_error"
    assert "down" in (transcript.error or "")
