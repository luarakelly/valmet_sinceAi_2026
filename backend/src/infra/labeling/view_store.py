"""Captured views on disk: <id>.jpg plus <id>.json (camera matrix, size)."""

import json
from pathlib import Path
import re
from typing import Any, Dict, List

VIEW_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class FileViewStore:
    def __init__(self, directory: Path):
        self._directory = directory

    def save(self, view_id: str, jpeg: bytes, meta: Dict[str, Any]) -> None:
        if not VIEW_ID_PATTERN.match(view_id):
            raise ValueError("Invalid view id: {!r}".format(view_id))
        self._directory.mkdir(parents=True, exist_ok=True)
        (self._directory / "{}.jpg".format(view_id)).write_bytes(jpeg)
        (self._directory / "{}.json".format(view_id)).write_text(json.dumps(meta))

    def view_ids(self) -> List[str]:
        return sorted(path.stem for path in self._directory.glob("*.jpg")) if self._directory.exists() else []
