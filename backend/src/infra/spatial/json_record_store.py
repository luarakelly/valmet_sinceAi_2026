"""Record store adapter: one JSON object per file in data/, written atomically."""

import json
import threading
from pathlib import Path
from typing import Any, Dict

from business.interfaces.ports.outbound.placement_store import PlacementStore
from business.interfaces.ports.outbound.verification_store import VerificationStore


class JsonRecordStore(VerificationStore, PlacementStore):
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()

    def all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return self._read()

    def save(self, key: str, record: Dict[str, Any]) -> None:
        with self._lock:
            records = self._read()
            records[key] = record
            self._write(records)

    def delete(self, key: str) -> None:
        with self._lock:
            records = self._read()
            records.pop(key, None)
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
