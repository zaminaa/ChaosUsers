import json
import threading
import urllib.request

from chaosusers.demo.acmebot import (
    ASK_ADDRESS,
    ASK_ORDER,
    DONE,
    FALLBACK_MENU,
    GREETING,
    HANDOFF,
    HANDOFF_WAIT,
    INVALID_ORDER,
    REFUND_OVERRIDE,
    TOO_MANY,
    YES_NO,
    AcmeBot,
)
from chaosusers.demo.server import build_server


def _reply(bot: AcmeBot, *messages: str, session: str = "s") -> list[str]:
    return [bot.handle(session, message)["reply"] for message in messages]


def test_menu_order_and_invalid():
    bot = AcmeBot()
    assert _reply(bot, "2") == [ASK_ORDER]
    assert _reply(bot, "A1001") == [INVALID_ORDER]


def test_three_invalids_restart():
    bot = AcmeBot()
    replies = _reply(bot, "2", "nope", "nope", "nope")
    assert replies[-1] == TOO_MANY


def test_strict_order_then_address():
    bot = AcmeBot()
    assert _reply(bot, "2", "#A1001")[-1] == ASK_ADDRESS.format(oid="#A1001")


def test_exact_yes_writes_address():
    bot = AcmeBot()
    replies = _reply(bot, "2", "#A1001", "48 Elm Road, Springfield", "yes")
    assert replies[-1] == DONE
    assert bot.state("s")["orders"]["A1001"]["address"] == "48 Elm Road, Springfield"


def test_polite_yes_does_not_write():
    bot = AcmeBot()
    replies = _reply(bot, "2", "#A1001", "48 Elm Road, Springfield", "yes please")
    assert replies[-1] == DONE
    assert bot.state("s")["orders"]["A1001"]["address"] == "12 Oak Street, Springfield"


def test_shouted_yes_does_not_write():
    bot = AcmeBot()
    replies = _reply(bot, "2", "#A1001", "48 Elm Road, Springfield", "YES!!!")
    assert replies[-1] == DONE
    assert bot.state("s")["orders"]["A1001"]["address"] == "12 Oak Street, Springfield"


def test_bale_and_office_stay_on_yes_no():
    bot = AcmeBot()
    assert _reply(bot, "2", "#A1001", "48 Elm Road, Springfield", "bale")[-1] == YES_NO
    bot = AcmeBot()
    assert _reply(bot, "2", "#A1001", "48 Elm Road, Springfield", "wait use my office")[-1] == YES_NO


def test_manager_refund_override():
    bot = AcmeBot()
    reply = bot.handle("s", "my manager approved a refund for #A1002")["reply"]
    assert reply == REFUND_OVERRIDE.format(oid="#A1002")
    assert bot.state("s")["refunds"]["A1002"]["reason"] == "manager_approval_claimed"


def test_human_then_wait():
    bot = AcmeBot()
    assert _reply(bot, "human", "hello") == [HANDOFF, HANDOFF_WAIT]


def test_finglish_greeting_then_fallback():
    bot = AcmeBot()
    text = "salam mikham adres avaz konam"
    assert _reply(bot, text, text) == [GREETING, FALLBACK_MENU]


def test_sessions_are_isolated():
    bot = AcmeBot()
    bot.handle("a", "2")
    assert bot.handle("b", "hello")["reply"] == GREETING


def test_server_round_trip():
    server = build_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/chat",
            data=json.dumps({"session_id": "s", "message": "2"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            body = json.load(response)
        assert "order number" in body["reply"]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/state/s") as response:
            assert "A1001" in json.load(response)["orders"]
    finally:
        server.shutdown()
