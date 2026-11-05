from chaosusers.llm.types import LLMRequest, Message, request_hash


def _req(**overrides) -> LLMRequest:
    data = {
        "purpose": "persona",
        "tag": "persona:example:r0",
        "model": "gpt-4.1-mini",
        "messages": [Message(role="user", content="hi")],
        "temperature": 0.9,
        "max_tokens": 300,
        "seed": 1,
    }
    data.update(overrides)
    return LLMRequest(**data)


def test_request_hash_ignores_field_order():
    left = request_hash(_req())
    raw = {
        "seed": 1,
        "max_tokens": 300,
        "temperature": 0.9,
        "messages": [{"content": "hi", "role": "user"}],
        "model": "gpt-4.1-mini",
        "tag": "persona:example:r0",
        "purpose": "persona",
    }
    right = request_hash(LLMRequest.model_validate(raw))
    assert left == right


def test_request_hash_changes_with_seed():
    assert request_hash(_req(seed=1)) != request_hash(_req(seed=2))
