from typing import Any, Dict, Protocol


class PlacementStore(Protocol):
    """Persistence for operator-confirmed asset boxes, keyed by asset id."""

    def all(self) -> Dict[str, Dict[str, Any]]:
        ...

    def save(self, key: str, record: Dict[str, Any]) -> None:
        ...

    def delete(self, key: str) -> None:
        ...
