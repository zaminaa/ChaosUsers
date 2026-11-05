import re


def normalize(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.lower()).strip()
    return collapsed.strip("\"'`.,;:!?()[]")
