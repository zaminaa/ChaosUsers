import json
import secrets
import threading
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


class RunRecorder:
    def __init__(self, out_dir: Path, mode: str):
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        self.run_id = f"{stamp}-{mode}-{secrets.token_hex(3)}"
        self.path = Path(out_dir) / self.run_id
        self.path.mkdir(parents=True)
        self._lock = threading.Lock()

    def append_jsonl(self, name: str, obj: BaseModel) -> None:
        line = json.dumps(obj.model_dump(mode="json"), ensure_ascii=False)
        with self._lock, (self.path / name).open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def write_json(self, name: str, obj: BaseModel | dict) -> None:
        payload = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
        (self.path / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def call_log_path(self) -> Path:
        return self.path / "llm_calls.jsonl"
