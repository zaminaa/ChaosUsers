import json
import threading
from pathlib import Path

import yaml

from chaosusers.llm.budget import estimate_tokens
from chaosusers.llm.types import LLMRequest, LLMResponse, request_hash


class CassetteMiss(Exception):
    def __init__(self, tag: str, request_hash: str):
        self.tag = tag
        self.request_hash = request_hash
        super().__init__(f"cassette miss for {tag} ({request_hash})")


class ScriptedProvider:
    name = "script"

    def __init__(self, script: dict[str, list[str]]):
        self.script = script
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_yaml(cls, path: Path) -> "ScriptedProvider":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls({key: list(value) for key, value in data.items()})

    def complete(self, req: LLMRequest) -> LLMResponse:
        with self._lock:
            lines = self._lines(req.tag)
            index = self._counts.get(req.tag, 0)
            self._counts[req.tag] = index + 1
        text = lines[min(index, len(lines) - 1)]
        tokens_in = sum(estimate_tokens(message.content) for message in req.messages)
        return LLMResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=estimate_tokens(text),
            cost_usd=0.0,
            model=req.model,
            cached=True,
            request_hash=request_hash(req),
        )

    def _lines(self, tag: str) -> list[str]:
        if tag in self.script:
            return self.script[tag]
        parts = tag.split(":")
        for end in range(len(parts) - 1, 0, -1):
            prefix = ":".join(parts[:end])
            if prefix in self.script:
                return self.script[prefix]
        if "default" in self.script:
            return self.script["default"]
        raise KeyError(tag)


class ReplayProvider:
    name = "replay"

    def __init__(self, cassette: Path):
        self._rows: dict[str, dict] = {}
        for line in Path(cassette).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            self._rows[row["request_hash"]] = row

    def complete(self, req: LLMRequest) -> LLMResponse:
        hashed = request_hash(req)
        row = self._rows.get(hashed)
        if row is None:
            raise CassetteMiss(req.tag, hashed)
        return LLMResponse(
            text=row["text"],
            tokens_in=int(row["tokens_in"]),
            tokens_out=int(row["tokens_out"]),
            cost_usd=0.0,
            model=row.get("model", req.model),
            cached=True,
            request_hash=hashed,
            latency_ms=int(row.get("latency_ms") or 0),
        )
