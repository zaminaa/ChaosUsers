import re
from pathlib import Path

import yaml

from chaosusers.gauntlet.judge import load_rubric

ROOT = Path("rubrics/calibration/gauntlet_v1")
_ARABIC = re.compile(r"[\u0600-\u06FF]")
_REQUIRED = {"id", "kind", "type", "passed", "description"}


def _scenarios():
    files = sorted(ROOT.glob("cal-*.yaml"))
    assert len(files) >= 12
    return [yaml.safe_load(path.read_text(encoding="utf-8")) for path in files]


def test_scenarios_are_multi_turn_and_unique():
    rows = _scenarios()
    firsts = []
    for row in rows:
        assert row["status"] == "draft"
        turns = row["turns"]
        assert 4 <= len(turns) <= 8
        assert turns[0]["role"] == "user"
        assert turns[0]["text"].strip()
        firsts.append(turns[0]["text"].strip())
    assert len(firsts) == len(set(firsts))


def test_every_scenario_has_deterministic_checks_and_silent_failures_exist():
    rows = _scenarios()
    silent = 0
    for row in rows:
        checks = row["deterministic_checks"]
        assert checks
        for item in checks:
            assert _REQUIRED <= set(item)
            assert isinstance(item["passed"], bool)
            assert item["description"].strip()
        assert row["expected_outcome"]
        if row["expected_outcome"] == "silent_failure":
            silent += 1
            passed = {item["id"]: item["passed"] for item in checks}
            assert passed.get("success_claim") is True
            assert any(item["kind"] == "success" and item["passed"] is False for item in checks)
    assert silent >= 3


def test_persian_pack_scenarios_use_persian_script():
    rows = [row for row in _scenarios() if row["pack"] == "core-fa"]
    assert len(rows) >= 4
    for row in rows:
        user_text = " ".join(turn["text"] for turn in row["turns"] if turn["role"] == "user")
        assert _ARABIC.search(user_text)


def test_human_labels_cover_the_rubric():
    rubric, _sha = load_rubric("gauntlet_v1")
    seen = {dim.id: set() for dim in rubric.dimensions}
    for row in _scenarios():
        for dim, label in row["human_labels"].items():
            seen[dim].add(label)
    for dim in rubric.dimensions:
        allowed = {label.id for label in dim.labels}
        assert seen[dim.id] == allowed
