import hashlib
import json
from typing import Literal, Protocol

from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    purpose: Literal["persona", "judge", "panel", "calibrate"]
    tag: str
    model: str
    messages: list[Message]
    temperature: float
    max_tokens: int
    seed: int | None = None


class LLMResponse(BaseModel):
    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model: str
    cached: bool = False
    request_hash: str
    latency_ms: int = 0


class Provider(Protocol):
    name: str

    def complete(self, req: LLMRequest) -> LLMResponse: ...


def request_hash(req: LLMRequest) -> str:
    """sha256 of the generation fields. Key order does not change the hash."""
    payload = {
        "model": req.model,
        "messages": [m.model_dump() for m in req.messages],
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "seed": req.seed,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
