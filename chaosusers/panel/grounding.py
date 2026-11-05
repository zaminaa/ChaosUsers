from chaosusers.panel.artifact import Artifact
from chaosusers.textutil import normalize


def ground_findings(resp, artifact: Artifact, visible: dict[str, str]):
    if resp.output is None:
        return resp
    full = {section.id: section.text for section in artifact.sections}
    for finding in resp.output.findings:
        finding.grounded = False
        quote = finding.artifact_quote
        if finding.section_id not in full:
            finding.ungrounded_reason = "unknown_section"
            continue
        if len(quote.split()) < 3:
            finding.ungrounded_reason = "too_short"
            continue
        if normalize(quote) in normalize(visible.get(finding.section_id, "")):
            finding.grounded = True
            finding.ungrounded_reason = None
            continue
        if normalize(quote) in normalize(full[finding.section_id]):
            finding.ungrounded_reason = "not_in_visible_text"
            continue
        finding.ungrounded_reason = "not_found"
    return resp
