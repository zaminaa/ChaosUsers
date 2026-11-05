import difflib
import re

from chaosusers.gauntlet.scenario import FactSpec
from chaosusers.packs.schema import EventName


def detect_events(
    bot_text: str,
    prior_bot_texts: list[str],
    prior_user_texts: list[str],
    fallback_patterns: list[str],
    facts: dict[str, FactSpec],
    step_index: int | None,
    max_step_index_so_far: int,
    reading_budget_words: int,
) -> list[EventName]:
    events: list[EventName] = ["turn"]
    if any(re.search(pattern, bot_text, re.IGNORECASE) for pattern in fallback_patterns):
        events.append("bot_fallback")
    if any(difflib.SequenceMatcher(None, bot_text, previous).ratio() >= 0.85 for previous in prior_bot_texts):
        events.append("bot_repeated")
    if len(bot_text.split()) > reading_budget_words:
        events.append("bot_long")
    if _asks_known_fact(bot_text, prior_user_texts, facts):
        events.append("bot_asks_known_fact")
    if step_index is not None and step_index > max_step_index_so_far:
        events.append("bot_progress")
    return events


def _asks_known_fact(bot_text: str, prior_user_texts: list[str], facts: dict[str, FactSpec]) -> bool:
    joined = "\n".join(prior_user_texts).lower()
    for fact in facts.values():
        if not fact.asked_by or re.search(fact.asked_by, bot_text, re.IGNORECASE) is None:
            continue
        needles = [fact.value, *fact.variants]
        if any(needle.lower() in joined for needle in needles if needle):
            return True
    return False
