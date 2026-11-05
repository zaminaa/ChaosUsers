import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from chaosusers.llm.budget import Budget, Pricing
from chaosusers.llm.client import LLMClient
from chaosusers.llm.providers import AnthropicProvider, OpenAICompatProvider
from chaosusers.llm.testing import ReplayProvider, ScriptedProvider

_OPENAI_URL = "https://api.openai.com/v1"
_OPENROUTER_URL = "https://openrouter.ai/api/v1"


class ConfigError(Exception):
    pass


class RunConfig(BaseModel):
    mode: Literal["gauntlet", "panel"]
    pack: str = "core-en"
    personas: list[str] | None = None
    repeats: int = 2
    judge_samples: int = 3
    max_usd: float = 1.00
    max_tokens: int = 400_000
    max_turns: int = 12
    concurrency: int = 4
    seed: int = 1234
    provider: str | None = None
    model: str | None = None
    judge_model: str | None = None
    base_url: str | None = None
    allow_unpriced: bool = False
    replay: Path | None = None
    script: Path | None = None
    out_dir: Path = Path("chaosusers-runs")
    target: str | None = None
    scenario: str | None = None
    artifact: str | None = None
    artifact_kind: Literal["page", "text", "botscript"] | None = None
    fail_under: Literal["A", "B", "C", "D"] | None = None
    dry_run: bool = False
    open_report: bool = False
    pace: float = 0.0


def resolve_models(cfg: RunConfig, env: Mapping[str, str] = os.environ) -> RunConfig:
    provider = cfg.provider or _env(env, "CHAOSUSERS_PROVIDER") or _detect_provider(env)
    model = cfg.model or _env(env, "CHAOSUSERS_MODEL")
    judge_model = cfg.judge_model or _env(env, "CHAOSUSERS_JUDGE_MODEL")
    base_url = cfg.base_url or _env(env, "CHAOSUSERS_BASE_URL") or _default_base(provider, env)
    if provider and not model:
        model = Pricing.load().default_model(provider)
    if not judge_model:
        judge_model = model
    return cfg.model_copy(
        update={"provider": provider, "model": model, "judge_model": judge_model, "base_url": base_url}
    )


def build_client(cfg: RunConfig, call_log: Path, env: Mapping[str, str] = os.environ) -> tuple[LLMClient, Budget]:
    if cfg.replay is not None:
        budget = _zero_budget(cfg)
        return LLMClient(ReplayProvider(cfg.replay), budget, call_log), budget
    if cfg.script is not None:
        budget = _zero_budget(cfg)
        return LLMClient(ScriptedProvider.from_yaml(cfg.script), budget, call_log), budget

    resolved = resolve_models(cfg, env)
    key = _api_key(resolved, env)
    if not resolved.provider or not resolved.model or not key:
        raise ConfigError("No API key found. Try the free offline demo: chaosusers demo")

    pricing = Pricing.load()
    pair = pricing.price(resolved.model)
    judge_pair = pricing.price(resolved.judge_model or resolved.model)
    if (pair is None or judge_pair is None) and not resolved.allow_unpriced:
        missing = resolved.model if pair is None else resolved.judge_model
        raise ConfigError(
            f"No price for model {missing}. Add it to pricing.yaml, "
            "or pass --allow-unpriced to enforce the token cap only."
        )
    if pair is None:
        budget = Budget(resolved.max_usd, resolved.max_tokens, None, None)
    else:
        budget = Budget(resolved.max_usd, resolved.max_tokens, pair[0], pair[1])

    if resolved.provider == "anthropic":
        provider = AnthropicProvider(key, base_url=resolved.base_url or "https://api.anthropic.com")
    elif resolved.provider == "openai":
        provider = OpenAICompatProvider(resolved.base_url or _OPENAI_URL, key)
    else:
        raise ConfigError(f"Unknown provider {resolved.provider}")
    return LLMClient(provider, budget, call_log), budget


def _zero_budget(cfg: RunConfig) -> Budget:
    return Budget(cfg.max_usd, cfg.max_tokens, 0.0, 0.0)


def _env(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    return value or None


def _detect_provider(env: Mapping[str, str]) -> str | None:
    if _env(env, "ANTHROPIC_API_KEY"):
        return "anthropic"
    if _env(env, "OPENAI_API_KEY") or _env(env, "OPENROUTER_API_KEY"):
        return "openai"
    return None


def _default_base(provider: str | None, env: Mapping[str, str]) -> str | None:
    if provider == "openai" and _env(env, "OPENROUTER_API_KEY") and not _env(env, "OPENAI_API_KEY"):
        return _OPENROUTER_URL
    if provider == "openai":
        return _OPENAI_URL
    return None


def _api_key(cfg: RunConfig, env: Mapping[str, str]) -> str | None:
    if _env(env, "CHAOSUSERS_API_KEY"):
        return env["CHAOSUSERS_API_KEY"]
    if cfg.provider == "anthropic":
        return _env(env, "ANTHROPIC_API_KEY")
    if cfg.base_url and "openrouter.ai" in cfg.base_url:
        return _env(env, "OPENROUTER_API_KEY") or _env(env, "OPENAI_API_KEY")
    return _env(env, "OPENAI_API_KEY") or _env(env, "OPENROUTER_API_KEY")
