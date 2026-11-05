import json

import pytest

from chaosusers.llm.budget import Budget
from chaosusers.llm.client import LLMClient
from chaosusers.llm.testing import CassetteMiss, ReplayProvider, ScriptedProvider
from chaosusers.llm.types import LLMRequest, Message


def _req(tag: str) -> LLMRequest:
    return LLMRequest(
        purpose="persona",
        tag=tag,
        model="gpt-4.1-mini",
        messages=[Message(role="user", content="hi")],
        temperature=0.2,
        max_tokens=20,
        seed=3,
    )


def test_script_resolves_exact_then_prefix_then_default():
    provider = ScriptedProvider(
        {
            "persona:tess:r0": ["exact"],
            "persona:tess": ["prefix"],
            "default": ["fallback"],
        }
    )
    assert provider.complete(_req("persona:tess:r0")).text == "exact"
    assert provider.complete(_req("persona:tess:r1")).text == "prefix"
    assert provider.complete(_req("other:x")).text == "fallback"


def test_script_counters_are_per_exact_tag():
    provider = ScriptedProvider({"persona": ["a", "b"]})
    assert provider.complete(_req("persona:a:r0")).text == "a"
    assert provider.complete(_req("persona:b:r0")).text == "a"
    assert provider.complete(_req("persona:a:r0")).text == "b"
    assert provider.complete(_req("persona:a:r0")).text == "b"


def test_replay_roundtrip_and_miss(tmp_path):
    log = tmp_path / "llm_calls.jsonl"
    script = ScriptedProvider({"persona:tess:r0": ["recorded"]})
    budget = Budget(max_usd=1, max_tokens=1000, price_in=None, price_out=None)
    LLMClient(script, budget, log).complete(_req("persona:tess:r0"))
    replay = ReplayProvider(log)
    again = replay.complete(_req("persona:tess:r0"))
    assert again.text == "recorded"
    assert again.cached is True
    assert again.cost_usd == 0.0
    missing = _req("persona:other:r0").model_copy(update={"seed": 99})
    with pytest.raises(CassetteMiss) as exc:
        replay.complete(missing)
    assert exc.value.tag == "persona:other:r0"
    saved = json.loads(log.read_text(encoding="utf-8"))
    assert saved["text"] == "recorded"


def test_from_yaml(tmp_path):
    path = tmp_path / "script.yaml"
    path.write_text("default:\n  - from-yaml\n", encoding="utf-8")
    provider = ScriptedProvider.from_yaml(path)
    assert provider.complete(_req("anything")).text == "from-yaml"
