from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple

from business.models.records import SceneFrame


class SceneEngine(Protocol):
    """Extracted 3D scene: frames, asset bindings and walkability (implemented in infra/spatial)."""

    @property
    def target_asset_id(self) -> str:
        ...

    def get_semantic_frames(self) -> List[SceneFrame]:
        ...

    def summary(self) -> Dict[str, Any]:
        ...

    def find_frame(self, identifier: str) -> Optional[SceneFrame]:
        ...

    def nearby(self, x: float, z: float, radius_m: float) -> List[SceneFrame]:
        ...

    def get_navigation_path(
        self, target_id: Optional[str] = None, start: Optional[Tuple[float, float]] = None
    ) -> Dict[str, Any]:
        """Raises KeyError (unknown target) or a route-not-found error."""
        ...

    def rebuild(self) -> "SceneEngine":
        ...

    def get_ply_path(self) -> Path:
        ...

    def get_mesh_path(self) -> Path:
        ...
