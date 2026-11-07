from typing import Any, Dict, List, Optional, Protocol


class VisualDetector(Protocol):
    """Open-vocabulary 2D detector for viewport snapshots (YOLO-World adapter)."""

    def analyze(self, image_bytes: bytes, classes: Optional[List[str]], confidence: float) -> Dict[str, Any]:
        """Raises ValueError for oversized images; other exceptions mean 'unavailable'."""
        ...
