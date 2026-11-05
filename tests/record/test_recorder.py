import json
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from chaosusers.record.recorder import RunRecorder


class _Row(BaseModel):
    n: int


def test_directory_name_and_concurrent_jsonl(tmp_path):
    recorder = RunRecorder(tmp_path, "gauntlet")
    assert len(recorder.run_id.split("-")[-1]) == 6
    assert "-gauntlet-" in recorder.run_id

    def write(n: int) -> None:
        recorder.append_jsonl("transcripts.jsonl", _Row(n=n))

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(write, range(8)))
    lines = (recorder.path / "transcripts.jsonl").read_text(encoding="utf-8").splitlines()
    assert sorted(json.loads(line)["n"] for line in lines) == list(range(8))
    assert recorder.call_log_path().name == "llm_calls.jsonl"
