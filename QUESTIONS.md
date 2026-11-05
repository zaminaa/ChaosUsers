# Questions

Append unresolved decisions here. Format: the question, the default applied, and why.

## DoD run

Defaults from the plan were applied: scripted demo cassettes (no API key in this session), calibration labels left `draft`, `core-fa` included, and MiroFish named only in the README hero line.

Checked locally: `uv run ruff check .`, `uv run pytest -q`, `chaosusers packs validate core-en`, `chaosusers packs validate core-fa`, `chaosusers demo --no-open`, `chaosusers demo panel --no-open`. The wheel check is `uv build` followed by an isolated `chaosusers demo --no-open`. CI on GitHub was not run from this machine. Nothing was tagged or published.
