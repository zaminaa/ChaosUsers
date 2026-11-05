import pytest

from chaosusers.config import ConfigError, RunConfig, build_client, resolve_models
from chaosusers.llm.testing import ReplayProvider


def test_flag_beats_env_beats_autodetect():
    flagged = resolve_models(
        RunConfig(mode="gauntlet", provider="openai", model="gpt-4.1", judge_model="gpt-4.1-mini"),
        {
            "CHAOSUSERS_PROVIDER": "anthropic",
            "CHAOSUSERS_MODEL": "claude-haiku-4-5",
            "CHAOSUSERS_JUDGE_MODEL": "claude-sonnet-4-5",
            "OPENAI_API_KEY": "oa",
            "ANTHROPIC_API_KEY": "ant",
        },
    )
    assert (flagged.provider, flagged.model, flagged.judge_model) == ("openai", "gpt-4.1", "gpt-4.1-mini")

    from_env = resolve_models(
        RunConfig(mode="gauntlet"),
        {"CHAOSUSERS_PROVIDER": "anthropic", "CHAOSUSERS_MODEL": "claude-haiku-4-5", "OPENAI_API_KEY": "oa"},
    )
    assert from_env.provider == "anthropic"
    assert from_env.model == "claude-haiku-4-5"
    assert from_env.judge_model == "claude-haiku-4-5"

    detected = resolve_models(RunConfig(mode="gauntlet"), {"OPENAI_API_KEY": "oa"})
    assert detected.provider == "openai"
    assert detected.model == "gpt-4.1-mini"
    assert detected.base_url == "https://api.openai.com/v1"
    assert detected.judge_model == "gpt-4.1-mini"


def test_openrouter_autodetect_sets_base_url():
    got = resolve_models(RunConfig(mode="panel"), {"OPENROUTER_API_KEY": "or-key"})
    assert got.provider == "openai"
    assert got.base_url == "https://openrouter.ai/api/v1"
    assert got.model == "gpt-4.1-mini"


def test_missing_key_message(tmp_path):
    with pytest.raises(ConfigError, match="No API key found. Try the free offline demo: chaosusers demo"):
        build_client(RunConfig(mode="gauntlet"), tmp_path / "calls.jsonl", {})


def test_unpriced_model_error(tmp_path):
    cfg = RunConfig(mode="gauntlet", provider="openai", model="mystery-model", base_url="https://example.test/v1")
    with pytest.raises(ConfigError, match="No price for model mystery-model"):
        build_client(cfg, tmp_path / "calls.jsonl", {"OPENAI_API_KEY": "sk"})


def test_replay_needs_no_key(tmp_path):
    cassette = tmp_path / "cassette.jsonl"
    cassette.write_text("", encoding="utf-8")
    client, budget = build_client(RunConfig(mode="gauntlet", replay=cassette), tmp_path / "calls.jsonl", {})
    assert isinstance(client.provider, ReplayProvider)
    assert budget.price_in == 0.0
    assert budget.price_out == 0.0
