import json


def extract_json(text: str) -> dict:
    cleaned = _strip_fence(text.strip())
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        span = _first_object(cleaned)
        try:
            value = json.loads(span)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError("JSON value is not an object")  # noqa: TRY004  # plan: non-dict is ValueError
    return value


def _strip_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    newline = text.find("\n")
    body = text[newline + 1 :] if newline != -1 else ""
    body = body.rstrip()
    if body.endswith("```"):
        body = body[:-3].rstrip()
    return body


def _first_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object")
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError("unbalanced JSON object")
