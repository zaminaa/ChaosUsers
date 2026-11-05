import json

import httpx
import pytest

from chaosusers.llm.providers import AnthropicProvider, OpenAICompatProvider, ProviderError
from chaosusers.llm.types import LLMRequest, Message


def _request() -> LLMRequest:
    return LLMRequest(
        purpose="persona",
        tag="persona:example:r0",
        model="demo-model",
        messages=[
            Message(role="system", content="be brief"),
            Message(role="system", content="be kind"),
            Message(role="user", content="hi"),
        ],
        temperature=0.9,
        max_tokens=300,
        seed=7,
    )


def test_openai_request_and_parse():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 2},
            },
        )

    provider = OpenAICompatProvider(
        "https://api.openai.com/v1", "sk-test", transport=httpx.MockTransport(handler)
    )
    response = provider.complete(_request())
    assert provider.name == "openai"
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["messages"][0]["role"] == "system"
    assert seen["body"]["seed"] == 7
    assert "response_format" not in seen["body"]
    assert response.text == "hello"
    assert response.tokens_in == 11
    assert response.tokens_out == 2
    assert response.cost_usd == 0.0


def test_anthropic_request_and_parse():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-api-key"]
        seen["version"] = request.headers["anthropic-version"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "hel"}, {"type": "text", "text": "lo"}],
                "usage": {"input_tokens": 4, "output_tokens": 1},
            },
        )

    provider = AnthropicProvider("sk-ant", transport=httpx.MockTransport(handler))
    response = provider.complete(_request())
    assert provider.name == "anthropic"
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["key"] == "sk-ant"
    assert seen["version"] == "2023-06-01"
    assert seen["body"]["system"] == "be brief\n\nbe kind"
    assert seen["body"]["messages"] == [{"role": "user", "content": "hi"}]
    assert "response_format" not in seen["body"]
    assert "seed" not in seen["body"]
    assert response.text == "hello"
    assert (response.tokens_in, response.tokens_out) == (4, 1)


def test_retries_429_twice(monkeypatch):
    sleeps = []
    monkeypatch.setattr("chaosusers.llm.providers.time.sleep", lambda seconds: sleeps.append(seconds))
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, text="slow down")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
        )

    provider = OpenAICompatProvider("https://example.test/v1", "k", transport=httpx.MockTransport(handler))
    assert provider.complete(_request()).text == "ok"
    assert sleeps == [2, 6]
    assert calls["n"] == 3


def test_400_raises_immediately(monkeypatch):
    monkeypatch.setattr("chaosusers.llm.providers.time.sleep", lambda _seconds: pytest.fail("slept"))

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad request body")

    provider = AnthropicProvider("k", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as exc:
        provider.complete(_request())
    assert exc.value.status == 400
    assert "bad request" in exc.value.body
