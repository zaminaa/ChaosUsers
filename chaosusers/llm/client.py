import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from chaosusers.llm.budget import Budget, estimate_tokens
from chaosusers.llm.jsonout import extract_json
from chaosusers.llm.types import LLMRequest, LLMResponse, Message, Provider

T = TypeVar("T")


class LLMOutputError(Exception):
    pass


class LLMClient:
    def __init__(self, provider: Provider, budget: Budget, call_log_path: Path | None):
        self.provider = provider
        self.budget = budget
        self.call_log_path = call_log_path
        self._log_lock = threading.Lock()

    def complete(self, req: LLMRequest) -> LLMResponse:
        estimated = sum(estimate_tokens(message.content) for message in req.messages)
        rid = self.budget.reserve(estimated, req.max_tokens)
        try:
            response = self.provider.complete(req)
        except Exception:
            self.budget.release(rid)
            raise
        if response.cached:
            self.budget.release(rid)
            response.cost_usd = 0.0
        else:
            response.cost_usd = self.budget.commit(rid, response.tokens_in, response.tokens_out)
        self._append_log(req, response)
        return response

    def complete_json(self, req: LLMRequest, validate: Callable[[dict], T], retries: int = 1) -> T:
        current = req
        error: Exception | None = None
        for attempt in range(retries + 1):
            response = self.complete(current)
            try:
                return validate(extract_json(response.text))
            except (ValueError, ValidationError) as exc:
                error = exc
                if attempt >= retries:
                    break
                current = current.model_copy(
                    update={
                        "messages": [
                            *current.messages,
                            Message(role="assistant", content=response.text),
                            Message(
                                role="user",
                                content=f"Your output was invalid: {exc}. Reply again with ONLY the JSON object.",
                            ),
                        ]
                    }
                )
        raise LLMOutputError(str(error))

    def _append_log(self, req: LLMRequest, response: LLMResponse) -> None:
        if self.call_log_path is None:
            return
        row = {
            "ts": datetime.now(UTC).isoformat(),
            "tag": req.tag,
            "purpose": req.purpose,
            "request_hash": response.request_hash,
            "model": req.model,
            "seed": req.seed,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "messages": [message.model_dump() for message in req.messages],
            "text": response.text,
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
            "cost_usd": response.cost_usd,
            "latency_ms": response.latency_ms,
            "cached": response.cached,
        }
        line = json.dumps(row, ensure_ascii=False)
        with self._log_lock:
            self.call_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.call_log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
