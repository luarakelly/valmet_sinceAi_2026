"""Scene use cases: frames, summary, anchors and proximity over the extracted 3D scene."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from business.errors import InvalidRequestError, NotFoundError
from business.interfaces.ports.outbound import AssetRepository, SceneEngine
from business.models.records import StateRecord

FAULTY_STATES = ("degraded", "attention_required")


class SceneService:
    def __init__(self, scene: SceneEngine, assets: AssetRepository):
        self._scene = scene
        self._assets = assets

    @property
    def engine(self) -> SceneEngine:
        return self._scene

    def frames(self) -> List[Dict[str, Any]]:
        return self._scene.get_semantic_frames()

    def summary(self) -> Dict[str, Any]:
        return self._scene.summary()

    def find_frame(self, identifier: str) -> Optional[Dict[str, Any]]:
        return self._scene.find_frame(identifier)

    def anchor(self, asset_id: str, state: Optional[StateRecord] = None) -> Optional[Dict[str, Any]]:
        """Anchor of the extracted object this asset is bound to (replaces the Excel placeholders)."""
        frame = self._scene.find_frame(asset_id)
        if frame is None or frame.get("asset_id") != asset_id:
            return None
        x, y, z = frame["pos"]
        width, height, depth = frame["size"]
        anchor = {
            "scene_anchor_id": frame["scene_id"],
            "asset_id": asset_id,
            "tag": frame["tag"],
            "area_id": frame["mapped_asset"]["area_id"],
            "x_local_m": x,
            "y_local_m": y,
            "z_local_m": z,
            "bbox_x_m": width,
            "bbox_y_m": height,
            "bbox_z_m": depth,
            "mapping_confidence": frame["mapping_confidence"],
            "mapping_status": "bound_to_extracted_{}".format(frame["label"].lower()),
            "scene_path": "/BoilerRoom/{}".format(frame["scene_id"]),
        }
        if state:
            anchor["health_score"] = state.get("health_score")
            anchor["condition_state"] = state.get("condition_state")
            anchor["issue_code"] = state.get("issue_code")
        return anchor

    def anchors(self) -> List[Dict[str, Any]]:
        states = self._assets.states()
        anchors = [
            self.anchor(frame["asset_id"], states.get(frame["asset_id"]))
            for frame in self._scene.get_semantic_frames()
            if frame["asset_id"]
        ]
        return sorted((a for a in anchors if a), key=lambda a: a["asset_id"])

    def proximity(self, x: float, z: float, radius_m: float) -> List[Dict[str, Any]]:
        """Assets whose object lies within radius_m of the avatar on the floor plane, nearest first."""
        states = self._assets.states()
        result = []
        for frame in self._scene.nearby(x, z, radius_m):
            state = states.get(frame["asset_id"])
            if state is None:
                continue
            result.append({
                "asset_id": frame["asset_id"],
                "tag": frame["tag"],
                "distance_m": frame["distance_m"],
                "health_score": state["health_score"],
                "condition_state": state["condition_state"],
                "issue_code": state["issue_code"],
                "is_faulty": state["condition_state"] in FAULTY_STATES,
                "anchor": self.anchor(frame["asset_id"], state),
            })
        return result

    def object_geometry(self, identifier: str) -> bytes:
        geometry = self._scene.get_object_geometry(identifier)
        if geometry is None:
            raise NotFoundError("No scene object matches '{}'.".format(identifier))
        return geometry

    def lift_box(self, view_projection: List[float], image_box: List[float]) -> Dict[str, Any]:
        box = self._scene.lift_box(view_projection, image_box)
        if box is None:
            raise InvalidRequestError("No solid surface inside that box. Draw it tighter around the object.")
        return box

    def re_extract(self) -> Dict[str, Any]:
        scene = self._scene.rebuild()
        return {**scene.summary(), "all_frames": scene.get_semantic_frames()}

    def viewer_cloud(self) -> Path:
        path = self._scene.get_ply_path()
        if not path.exists():
            raise NotFoundError("Boiler room PLY not found on server")
        return path

    def viewer_splat(self) -> Path:
        try:
            return self._scene.get_splat_path()
        except FileNotFoundError as error:
            raise NotFoundError(str(error)) from error

    def viewer_mesh(self) -> Path:
        """Served as-is; rebuild offline with scripts/build_mesh.py (minutes, extra deps)."""
        path = self._scene.get_mesh_path()
        if not path.exists():
            raise NotFoundError("Boiler room mesh not found; run scripts/build_mesh.py")
        return path
