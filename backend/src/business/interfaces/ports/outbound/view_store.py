from typing import Any, Dict, List, Protocol


class ViewStore(Protocol):
    """Rendered viewer images with the exact camera matrix that produced them."""

    def save(self, view_id: str, jpeg: bytes, meta: Dict[str, Any]) -> None:
        ...

    def view_ids(self) -> List[str]:
        ...
