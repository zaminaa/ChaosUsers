import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from chaosusers.llm.budget import Budget
from chaosusers.llm.client import LLMClient, LLMOutputError
from chaosusers.llm.testing import ScriptedProvider
from chaosusers.llm.types import LLMRequest, LLMResponse, Message, request_hash


class _Out(BaseModel):
    n: int


class _Priced:
    name = "priced"

    def complete(self, req: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text="done",
            tokens_in=1000,
            tokens_out=500,
            cost_usd=0.0,
            model=req.model,
            request_hash=request_hash(req),
            cached=False,
        )


class _Blocked:
    name = "blocked"

    def complete(self, req: LLMRequest) -> LLMResponse:
        raise AssertionError(req.tag)


def _req(tag: str = "persona:example:r0", text: str = "hi", max_tokens: int = 300) -> LLMRequest:
    return LLMRequest(
        purpose="persona",
        tag=tag,
        model="gpt-4.1-mini",
        messages=[Message(role="user", content=text)],
        temperature=0.9,
        max_tokens=max_tokens,
        seed=1,
    )


def _budget(**kwargs) -> Budget:
    data = {"max_usd": 1.0, "max_tokens": 1_000_000, "price_in": 0.40, "price_out": 1.60}
    data.update(kwargs)
    return Budget(**data)


def test_client_charges_and_logs(tmp_path: Path):
    log = tmp_path / "llm_calls.jsonl"
    client = LLMClient(_Priced(), _budget(), log)
    response = client.complete(_req())
    assert response.cost_usd == 0.0012
    assert client.budget.spent_usd == 0.0012
    line = json.loads(log.read_text(encoding="utf-8"))
    assert line["tag"] == "persona:example:r0"
    assert line["text"] == "done"
    assert line["cost_usd"] == 0.0012
    assert line["cached"] is False
    assert line["request_hash"] == request_hash(_req())


def test_cached_responses_cost_nothing(tmp_path: Path):
    script = ScriptedProvider({"persona:example:r0": ["hello"]})
    client = LLMClient(script, _budget(), tmp_path / "calls.jsonl")
    response = client.complete(_req())
    assert response.cached is True
    assert response.cost_usd == 0.0
    assert client.budget.spent_usd == 0.0


def test_complete_json_retries_once(tmp_path: Path):
    script = ScriptedProvider({"persona:example:r0": ["nope", '{"n": 1}']})
    client = LLMClient(script, _budget(), tmp_path / "calls.jsonl")
    parsed = client.complete_json(_req(), _Out.model_validate)
    assert parsed.n == 1
    lines = (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    second = json.loads(lines[1])
    joined = " ".join(message["content"] for message in second["messages"])
    assert "nope" in joined
    assert "Your output was invalid" in joined


def test_complete_json_raises_after_retry(tmp_path: Path):
    script = ScriptedProvider({"persona:example:r0": ["nope", "still nope"]})
    client = LLMClient(script, _budget(), tmp_path / "calls.jsonl")
    with pytest.raises(LLMOutputError):
        client.complete_json(_req(), _Out.model_validate)
    assert len((tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_budget_block_writes_no_log(tmp_path: Path):
    log = tmp_path / "calls.jsonl"
    client = LLMClient(_Blocked(), _budget(max_usd=0.0001, max_tokens=10), log)
    with pytest.raises(Exception, match="usd cap|token cap") as exc:
        client.complete(_req(max_tokens=300))
    assert exc.type.__name__ == "BudgetExceeded"
    assert not log.exists()


def test_validation_error_is_retried(tmp_path: Path):
    script = ScriptedProvider({"persona:example:r0": ['{"n": "x"}', '{"n": 2}']})
    client = LLMClient(script, _budget(), tmp_path / "calls.jsonl")
    assert client.complete_json(_req(), _Out.model_validate).n == 2
