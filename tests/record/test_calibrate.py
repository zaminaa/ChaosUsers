import json
from pathlib import Path

import yaml

from chaosusers.llm.budget import Budget
from chaosusers.llm.client import LLMClient
from chaosusers.llm.testing import ScriptedProvider
from chaosusers.record.calibrate import calibrate

ROOT = Path("rubrics/calibration/gauntlet_v1")


def _client(flip: str | None = None) -> LLMClient:
    script = {}
    for path in sorted(ROOT.glob("cal-*.yaml")):
        sample = yaml.safe_load(path.read_text(encoding="utf-8"))
        body = {}
        for dim, label in sample["human_labels"].items():
            if flip and sample["id"] == "cal-01" and dim == "task_completed":
                label = flip
            body[dim] = {"label": label, "evidence": [{"turn": 2, "quote": "Reply with a number"}], "rationale": "ok"}
        script[f"judge:{sample['id']}:r0:s0"] = [json.dumps(body)]
    return LLMClient(ScriptedProvider(script), Budget(1, 100_000, 0, 0), None)


def test_scripted_labels_match_and_a_flip_drops_agreement():
    perfect = calibrate("gauntlet_v1", _client(), "scripted-test", samples=1)
    assert perfect["overall"] == 1.0
    assert perfect["labels_status"] == "draft"
    assert (ROOT / "results" / "scripted-test.json").is_file()
    flipped = calibrate("gauntlet_v1", _client("no"), "scripted-test", samples=1)
    assert flipped["per_dim"]["task_completed"] < 1.0
