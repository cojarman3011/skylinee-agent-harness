import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any


class AuditLogger:
    def __init__(self, path: Path, log_prompt_content: bool = False) -> None:
        self.path = path
        self.log_prompt_content = log_prompt_content
        self._lock = Lock()

    def fingerprint(self, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def write(
        self, event: dict[str, Any], payload: dict[str, Any] | None = None
    ) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            **event,
        }
        if payload is not None:
            record["request_sha256"] = self.fingerprint(payload)
            if self.log_prompt_content:
                record["payload"] = payload

        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, default=str) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
