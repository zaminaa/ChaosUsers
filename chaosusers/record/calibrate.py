import json
from datetime import UTC, datetime

import yaml

from chaosusers.gauntlet.driver import Transcript, Turn
from chaosusers.gauntlet.judge import judge_transcript, load_rubric
from chaosusers.paths import data_root


def latest_calibration(rubric_id: str, model: str) -> dict | None:
    slug = model.replace("/", "-").replace(":", "-")
    path = data_root() / "rubrics" / "calibration" / rubric_id / "results" / f"{slug}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def calibrate(rubric_id: str, client, model: str, samples: int = 3) -> dict:
    rubric, _sha = load_rubric(rubric_id)
    folder = data_root() / "rubrics" / "calibration" / rubric_id
    files = sorted(folder.glob("cal-*.yaml"))
    per_dim_hits = {dim.id: [0, 0] for dim in rubric.dimensions}
    labels_status = "draft"
    for path in files:
        sample = yaml.safe_load(path.read_text(encoding="utf-8"))
        labels_status = sample.get("status") or labels_status
        transcript = Transcript(
            conversation_id=sample["id"], persona_id=sample["id"], scenario_id="calibration", repeat=0, seed=1,
            remembered_facts={}, end_reason="persona_done",
            turns=[Turn(index=turn["index"], role=turn["role"], text=turn["text"]) for turn in sample["turns"]],
        )
        consensus, _ungrounded = judge_transcript(transcript, rubric, client, model, samples, 1)
        for dim, human in sample["human_labels"].items():
            per_dim_hits[dim][1] += 1
            if consensus.get(dim) and consensus[dim].label == human:
                per_dim_hits[dim][0] += 1
    per_dim = {dim: (hits / total if total else 0.0) for dim, (hits, total) in per_dim_hits.items()}
    overall = sum(per_dim.values()) / len(per_dim) if per_dim else 0.0
    result = {
        "rubric": rubric_id, "model": model, "date": datetime.now(UTC).date().isoformat(),
        "samples": samples, "labels_status": labels_status, "per_dim": per_dim,
        "overall": overall, "n_transcripts": len(files),
    }
    slug = model.replace("/", "-").replace(":", "-")
    out = folder / "results" / f"{slug}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
