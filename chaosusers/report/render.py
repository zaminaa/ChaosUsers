import json
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

_ENV = Environment(
    loader=PackageLoader("chaosusers.report", "templates"),
    autoescape=select_autoescape(["html", "svg", "j2"]),
)


def load_run(run_dir: Path) -> dict:
    root = Path(run_dir)
    run = {
        "manifest": _read(root / "manifest.json"),
        "scores": _read(root / "scores.json"),
        "predictions": _read(root / "predictions.json"),
    }
    transcripts = root / "transcripts.jsonl"
    if transcripts.is_file():
        run["transcripts"] = [json.loads(line) for line in transcripts.read_text(encoding="utf-8").splitlines() if line.strip()]
    responses = root / "panel_responses.jsonl"
    if responses.is_file():
        run["panel_responses"] = [json.loads(line) for line in responses.read_text(encoding="utf-8").splitlines() if line.strip()]
    artifact = root / "artifact.json"
    if artifact.is_file():
        run["artifact"] = _read(artifact)
    verification = root / "verification.json"
    if verification.is_file():
        run["verification"] = _read(verification)
    return run


def render_gauntlet_report(run: dict) -> str:
    return _ENV.get_template("gauntlet.html.j2").render(**run, receipt=_receipt(run))


def render_panel_report(run: dict) -> str:
    return _ENV.get_template("panel.html.j2").render(**run, receipt=_receipt(run))


def render_card(run: dict) -> str:
    return _ENV.get_template("card.svg.j2").render(**run, receipt=_receipt(run), quote=_quote(run))


def render_badge(run: dict) -> str:
    grade = (run.get("scores") or {}).get("grade") or "UNGRADED"
    return _ENV.get_template("badge.svg.j2").render(grade=grade)


def write_reports(run_dir: Path) -> None:
    run = load_run(run_dir)
    html = render_gauntlet_report(run) if run["manifest"]["mode"] == "gauntlet" else render_panel_report(run)
    Path(run_dir, "report.html").write_text(html, encoding="utf-8")
    Path(run_dir, "card.svg").write_text(render_card(run), encoding="utf-8")
    Path(run_dir, "badge.svg").write_text(render_badge(run), encoding="utf-8")


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _receipt(run: dict) -> str:
    return (run.get("manifest") or {}).get("predictions_sha256") or ""


def _quote(run: dict) -> str:
    for item in (run.get("scores") or {}).get("conversations") or []:
        highlight = item.get("highlight") or {}
        if highlight.get("user"):
            text = f"{highlight['user']} → {highlight.get('bot', '')}".replace("✅", "✓")
            text = "".join(char for char in text if ord(char) <= 0xFFFF)
            return (text[:89] + "…") if len(text) > 90 else text
    return ""
