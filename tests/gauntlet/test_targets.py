import json
import threading

import httpx
import pytest

from chaosusers.demo.server import build_server
from chaosusers.gauntlet.driver import Turn
from chaosusers.gauntlet.targets import HttpTarget, TargetError, load_target


def test_http_target_against_acmebot():
    server = build_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        target = HttpTarget(
            {
                "name": "local",
                "url": f"http://127.0.0.1:{port}/chat",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "body": {"session_id": "{{session_id}}", "message": "{{message}}"},
                "reply_path": "reply",
                "state_url": f"http://127.0.0.1:{port}/state/{{{{session_id}}}}",
            }
        )
        reply = target.send("s", "2", [])
        assert "order number" in reply.text
        assert "A1001" in target.state("s")["orders"]
    finally:
        server.shutdown()


def test_header_env_and_describe_hides_secret(monkeypatch):
    monkeypatch.setenv("ACME_TOKEN", "super-secret-token")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"reply": "ok"})

    target = HttpTarget(
        {
            "name": "secured",
            "url": "https://example.test/chat?token=nope",
            "headers": {"Authorization": "Bearer ${ACME_TOKEN}"},
            "body": {"session_id": "{{session_id}}", "messages": "{{messages_json}}"},
            "reply_path": "reply",
        },
        transport=httpx.MockTransport(handler),
    )
    history = [Turn(index=1, role="user", text="hi"), Turn(index=2, role="bot", text="hello")]
    assert target.send("abc", "next", history).text == "ok"
    assert seen["auth"] == "Bearer super-secret-token"
    assert seen["body"]["messages"][0] == {"role": "user", "content": "hi"}
    assert seen["body"]["messages"][-1] == {"role": "user", "content": "next"}
    described = json.dumps(target.describe())
    assert "super-secret-token" not in described
    assert "token=nope" not in described
    monkeypatch.delenv("ACME_TOKEN")
    with pytest.raises(TargetError, match="ACME_TOKEN"):
        target.send("abc", "next", [])


def test_reply_path_on_openai_shape():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "from-model"}}]})

    target = HttpTarget(
        {"name": "oa", "url": "https://example.test/v1/chat/completions", "body": {"message": "{{message}}"}, "reply_path": "choices.0.message.content"},
        transport=httpx.MockTransport(handler),
    )
    assert target.send("s", "hi", []).text == "from-model"


def test_demo_alias_loads_python_target():
    target = load_target("demo")
    assert target.name == "AcmeBot (demo)"
    assert target.has_state is True
