# Contributing

```
uv sync --group dev
uv run ruff check .
uv run pytest -q
uv run chaosusers packs validate core-en
uv run chaosusers packs validate core-fa
```

A persona pull request should cite a taxonomy class, follow that class's respect note, pass `chaosusers packs validate`, contain no real names or contact data, and keep the example utterance inside the persona's fidelity rules.

Any wording change to a rubric bumps its version and needs a fresh calibration run. Do not mark calibration labels `approved`; that is the maintainer's review.
