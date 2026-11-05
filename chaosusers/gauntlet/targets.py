import importlib
import os
import re
from typing import Protocol
from urllib.parse import urlsplit

import httpx
import yaml
from pydantic import BaseModel

from chaosusers.paths import resolve_data_path

_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class TargetError(Exception):
    pass


class TargetReply(BaseModel):
    text: str
    latency_ms: int = 0
    raw: dict | None = None


class Target(Protocol):
    name: str
    has_state: bool

    def start(self, session_id: str) -> None: ...

    def send(self, session_id: str, message: str, history: list) -> TargetReply: ...

    def state(self, session_id: str) -> dict | None: ...

    def describe(self) -> dict: ...


class PythonTarget:
    def __init__(self, name: str, bot, has_state: bool = True):
        self.name = name
        self.bot = bot
        self.has_state = has_state

    def start(self, session_id: str) -> None:
        return None

    def send(self, session_id: str, message: str, history: list) -> TargetReply:
        result = self.bot.handle(session_id, message)
        return TargetReply(text=result["reply"], latency_ms=0, raw=result)

    def state(self, session_id: str) -> dict | None:
        return self.bot.state(session_id)

    def describe(self) -> dict:
        return {"adapter": "python", "name": self.name, "url_without_query": "", "has_state": self.has_state}


class HttpTarget:
    def __init__(self, spec: dict, transport: httpx.BaseTransport | None = None):
        self.name = spec["name"]
        self.url = spec["url"]
        self.method = spec.get("method", "POST")
        self._header_template = dict(spec.get("headers") or {})
        self._body_template = spec.get("body") or {}
        self.reply_path = spec.get("reply_path", "reply")
        self.state_url = spec.get("state_url")
        self.timeout_s = spec.get("timeout_s", 20)
        self.has_state = bool(self.state_url)
        self._client = _client(self.timeout_s, transport)

    def start(self, session_id: str) -> None:
        return None

    def send(self, session_id: str, message: str, history: list) -> TargetReply:
        body = _render(self._body_template, session_id, message, history)
        headers = {key: _resolve_env(value) for key, value in self._header_template.items()}
        try:
            response = self._client.request(self.method, self.url, json=body, headers=headers)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise TargetError(str(exc)) from exc
        return TargetReply(text=str(_dig(payload, self.reply_path)), latency_ms=0, raw=payload)

    def state(self, session_id: str) -> dict | None:
        if not self.state_url:
            return None
        url = _render(self.state_url, session_id, "", [])
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TargetError(str(exc)) from exc
        return response.json()

    def describe(self) -> dict:
        parts = urlsplit(self.url)
        return {
            "adapter": "http",
            "name": self.name,
            "url_without_query": f"{parts.scheme}://{parts.netloc}{parts.path}",
            "has_state": self.has_state,
        }


class OpenAIChatTarget:
    def __init__(self, spec: dict, transport: httpx.BaseTransport | None = None):
        self.name = spec["name"]
        self.base_url = spec["base_url"].rstrip("/")
        self.model = spec["model"]
        self.api_key_env = spec["api_key_env"]
        self.temperature = spec.get("temperature", 0.3)
        prompt_path = resolve_data_path(spec["system_prompt_file"])
        self._system = prompt_path.read_text(encoding="utf-8")
        self.has_state = False
        self._client = _client(60, transport)

    def start(self, session_id: str) -> None:
        return None

    def send(self, session_id: str, message: str, history: list) -> TargetReply:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise TargetError(f"env var {self.api_key_env} not set")
        messages = [{"role": "system", "content": self._system}, *_chat_history(history), {"role": "user", "content": message}]
        try:
            response = self._client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": self.model, "messages": messages, "temperature": self.temperature},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise TargetError(str(exc)) from exc
        return TargetReply(text=str(_dig(payload, "choices.0.message.content")), latency_ms=0, raw=payload)

    def state(self, session_id: str) -> dict | None:
        return None

    def describe(self) -> dict:
        parts = urlsplit(self.base_url)
        return {
            "adapter": "openai_chat",
            "name": self.name,
            "url_without_query": f"{parts.scheme}://{parts.netloc}{parts.path}",
            "has_state": False,
        }


def load_target(spec: str, transport: httpx.BaseTransport | None = None) -> Target:
    path = resolve_data_path("examples/targets/acme-demo.yaml" if spec == "demo" else spec)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    adapter = data["adapter"]
    if adapter == "python":
        module_name, func_name = data["factory"].split(":")
        return getattr(importlib.import_module(module_name), func_name)()
    if adapter == "http":
        return HttpTarget(data, transport=transport)
    if adapter == "openai_chat":
        return OpenAIChatTarget(data, transport=transport)
    raise TargetError(f"unknown adapter {adapter}")


def _client(timeout: float, transport: httpx.BaseTransport | None) -> httpx.Client:
    if transport is not None:
        return httpx.Client(timeout=timeout, transport=transport)
    # shortcut: loopback bypasses HTTP_PROXY; upgrade if a target must use a proxy on localhost
    return httpx.Client(
        timeout=timeout,
        mounts={
            "http://127.0.0.1": httpx.HTTPTransport(),
            "http://localhost": httpx.HTTPTransport(),
        },
    )


def _render(value, session_id: str, message: str, history: list):
    if isinstance(value, str):
        if value == "{{messages_json}}":
            return _chat_history(history) + [{"role": "user", "content": message}]
        return value.replace("{{session_id}}", session_id).replace("{{message}}", message)
    if isinstance(value, dict):
        return {key: _render(item, session_id, message, history) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item, session_id, message, history) for item in value]
    return value


def _chat_history(history: list) -> list[dict]:
    messages = []
    for turn in history:
        role = getattr(turn, "role", None) or turn.get("role")
        text = getattr(turn, "text", None)
        if text is None:
            text = turn.get("content", turn.get("text", ""))
        if role == "user":
            messages.append({"role": "user", "content": text})
        elif role == "bot":
            messages.append({"role": "assistant", "content": text})
    return messages


def _resolve_env(value: str) -> str:
    def replace(match: re.Match) -> str:
        name = match.group(1)
        found = os.environ.get(name)
        if not found:
            raise TargetError(f"env var {name} not set")
        return found

    return _ENV.sub(replace, value)


def _dig(payload, path: str):
    current = payload
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    return current
