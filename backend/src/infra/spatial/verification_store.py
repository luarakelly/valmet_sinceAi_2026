"""VerificationStore adapter: one JSON file in data/, written atomically."""

import json
import threading
from pathlib import Path
from typing import Any, Dict

from business.interfaces.ports.outbound.verification_store import VerificationStore
from infra.paths import DATA_DIR

VERIFICATION_PATH = DATA_DIR / "object_verification.json"


class JsonVerificationStore(VerificationStore):
    def __init__(self, path: Path = VERIFICATION_PATH):
        self._path = path
        self._lock = threading.Lock()

    def all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return self._read()

    def save(self, object_id: str, record: Dict[str, Any]) -> None:
        with self._lock:
            records = self._read()
            records[object_id] = record
            self._write(records)

    def clear(self) -> None:
        with self._lock:
            self._write({})

    def _read(self) -> Dict[str, Dict[str, Any]]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write(self, records: Dict[str, Dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(records, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(self._path)
