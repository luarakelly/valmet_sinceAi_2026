from typing import Any, Dict, Protocol


class VerificationStore(Protocol):
    """Persistence for camera verification results, keyed by scene object id (OBJ-xxx)."""

    def all(self) -> Dict[str, Dict[str, Any]]:
        ...

    def save(self, object_id: str, record: Dict[str, Any]) -> None:
        ...

    def clear(self) -> None:
        ...
