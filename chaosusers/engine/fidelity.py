import re

from chaosusers.packs.schema import PersonaSpec

_ARABIC = re.compile(r"[\u0600-\u06FF]")


def check_fidelity(text: str, spec: PersonaSpec) -> list[str]:
    rules = spec.fidelity
    issues: list[str] = []
    if rules.max_words is not None and len(text.split()) > rules.max_words:
        issues.append(f"max_words:{rules.max_words}")
    if rules.require_script == "Latin" and _ARABIC.search(text):
        issues.append("script:expected Latin")
    if rules.require_script == "Arabic":
        letters = [char for char in text if char.isalpha()]
        if letters and _ARABIC.search(text) is None:
            issues.append("script:expected Arabic")
    for word in rules.forbidden_words:
        if re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE):
            issues.append(f"forbidden_word:{word}")
    return issues
