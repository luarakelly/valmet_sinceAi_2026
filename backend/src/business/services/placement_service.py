"""Operator placements: the team boxes each asset in the viewer once, and the scene binds it with certainty.

The workbook has no real positions, so this is the ground truth that overrides every guess.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from business.errors import InvalidRequestError, NotFoundError
from business.interfaces.ports.outbound import AssetRepository, PlacementStore
from business.services.scene_service import SceneService


class PlacementService:
    def __init__(self, assets: AssetRepository, scene: SceneService, store: PlacementStore):
        self._assets = assets
        self._scene = scene
        self._store = store

    def all(self) -> Dict[str, Dict[str, Any]]:
        return self._store.all()

    def lift(self, view_projection: List[float], image_box: List[float]) -> Dict[str, Any]:
        return self._scene.lift_box(view_projection, image_box)

    def save(self, asset_id: str, center: List[float], size: List[float], status: str) -> Dict[str, Any]:
        asset = self._assets.find(asset_id)
        if asset is None:
            raise NotFoundError("No asset matches '{}'.".format(asset_id))
        if not all(side > 0 for side in size):
            raise InvalidRequestError("A placement box needs a positive size on every axis.")
        record = {
            "center": [round(float(v), 3) for v in center],
            "size": [round(float(v), 3) for v in size],
            "status": status,
            "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._store.save(asset["asset_id"], record)
        self._scene.re_extract()
        return {"asset_id": asset["asset_id"], **record}

    def delete(self, asset_id: str) -> None:
        self._store.delete(asset_id)
        self._scene.re_extract()
