import time

import httpx

from chaosusers.llm.types import LLMRequest, LLMResponse, request_hash


class ProviderError(Exception):
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")


def _post(client: httpx.Client, url: str, body: dict, headers: dict[str, str]) -> httpx.Response:
    response: httpx.Response | None = None
    for attempt in range(3):
        response = client.post(url, json=body, headers=headers)
        retryable = response.status_code == 429 or response.status_code >= 500
        if retryable and attempt < 2:
            time.sleep((2, 6)[attempt])
            continue
        if response.status_code >= 400:
            raise ProviderError(response.status_code, response.text[:500])
        return response
    assert response is not None
    raise ProviderError(response.status_code, response.text[:500])


class OpenAICompatProvider:
    name = "openai"

    def __init__(self, base_url: str, api_key: str, transport: httpx.BaseTransport | None = None):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(timeout=60, transport=transport)

    def complete(self, req: LLMRequest) -> LLMResponse:
        body: dict = {
            "model": req.model,
            "messages": [message.model_dump() for message in req.messages],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        }
        if req.seed is not None:
            body["seed"] = req.seed
        payload = _post(
            self._client,
            f"{self._base_url}/chat/completions",
            body,
            {"Authorization": f"Bearer {self._api_key}"},
        ).json()
        usage = payload.get("usage") or {}
        content = payload["choices"][0]["message"]["content"]
        return _response(req, content or "", int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0))


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        transport: httpx.BaseTransport | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(timeout=60, transport=transport)

    def complete(self, req: LLMRequest) -> LLMResponse:
        system = "\n\n".join(message.content for message in req.messages if message.role == "system")
        messages = [
            {"role": message.role, "content": message.content}
            for message in req.messages
            if message.role != "system"
        ]
        body: dict = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "messages": messages,
        }
        if system:
            body["system"] = system
        payload = _post(
            self._client,
            f"{self._base_url}/v1/messages",
            body,
            {"x-api-key": self._api_key, "anthropic-version": "2023-06-01"},
        ).json()
        text = "".join(block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text")
        usage = payload.get("usage") or {}
        return _response(req, text, int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0))


def _response(req: LLMRequest, text: str, tokens_in: int, tokens_out: int) -> LLMResponse:
    return LLMResponse(
        text=text,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=0.0,
        model=req.model,
        request_hash=request_hash(req),
    )
