import re

_DROP = {"run_id", "created_at", "latency_ms", "cost_usd", "usd", "ts"}
_SHA = re.compile(r"^[0-9a-f]{64}$")


def normalize_for_golden(obj):
    if isinstance(obj, dict):
        return {key: normalize_for_golden(value) for key, value in obj.items() if key not in _DROP}
    if isinstance(obj, list):
        return [normalize_for_golden(item) for item in obj]
    if isinstance(obj, str) and _SHA.match(obj):
        return "<sha>"
    return obj
