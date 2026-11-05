from collections import defaultdict

from chaosusers.panel.artifact import Artifact
from chaosusers.panel.models import PanelResponse


def aggregate_panel(responses: list[PanelResponse], artifact: Artifact, repeats: int, status: str) -> dict:
    by_persona: dict[str, list[PanelResponse]] = defaultdict(list)
    for response in responses:
        by_persona[response.persona_id].append(response)
    verdicts = {}
    for persona_id, rows in by_persona.items():
        counts: dict[str, int] = defaultdict(int)
        for row in rows:
            if row.output:
                counts[row.output.verdict] += 1
        if not counts:
            verdicts[persona_id] = "split"
            continue
        best = max(counts.values())
        winners = [name for name, count in counts.items() if count == best]
        verdicts[persona_id] = winners[0] if len(winners) == 1 else "split"
    friction = []
    ungrounded = []
    for section in artifact.sections:
        personas = []
        types: dict[str, int] = defaultdict(int)
        stable = []
        score = 0.0
        quotes = []
        for persona_id, rows in by_persona.items():
            grounded = []
            for row in rows:
                if not row.output:
                    continue
                for finding in row.output.findings:
                    if finding.section_id != section.id:
                        continue
                    if not finding.grounded:
                        ungrounded.append({
                            "persona_id": persona_id, "section_id": section.id,
                            "artifact_quote": finding.artifact_quote, "reason": finding.ungrounded_reason,
                        })
                        continue
                    grounded.append(finding)
                    types[finding.type] += 1
            if not grounded:
                continue
            personas.append(persona_id)
            keys = {(finding.section_id, finding.type) for finding in grounded}
            is_stable = len(rows) >= repeats and len(keys) == 1 and all(
                any(item.grounded and item.section_id == section.id and item.type == next(iter(keys))[1] for item in (row.output.findings if row.output else []))
                for row in rows
            )
            if is_stable:
                stable.append(persona_id)
            severity = max(finding.severity for finding in grounded)
            score += severity * (1.0 if is_stable else 0.5)
            best = max(grounded, key=lambda finding: finding.severity)
            quotes.append({
                "persona_id": persona_id, "in_character_quote": best.in_character_quote,
                "artifact_quote": best.artifact_quote, "severity": best.severity, "stable": is_stable,
            })
        if personas:
            friction.append({
                "section_id": section.id, "title": section.title, "personas": sorted(personas),
                "types": dict(types), "stable_personas": sorted(stable), "score": score,
                "best_quotes": sorted(quotes, key=lambda item: -item["severity"])[:3],
            })
    friction.sort(key=lambda item: -item["score"])
    abandon = defaultdict(int)
    for persona_id, verdict in verdicts.items():
        if verdict != "would_abandon":
            continue
        points = [row.output.abandon_at for row in by_persona[persona_id] if row.output and row.output.abandon_at]
        if points:
            abandon[max(set(points), key=points.count)] += 1
    return {
        "verdicts": verdicts,
        "abandon_points": dict(abandon),
        "friction": friction,
        "top_failures": friction[:5],
        "ungrounded": ungrounded,
        "invalid_responses": sum(not row.valid for row in responses),
        "status": status,
        "words_read": {row.persona_id: row.words_read for row in responses},
    }
