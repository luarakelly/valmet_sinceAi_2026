from typing import Any, Dict, List

from fastapi import Depends
from fastapi.responses import FileResponse

from api.container import Container, get_container
from api.controllers.errors import http_errors
from dto.asset_dto import SceneAnchorRead
from dto.scene_dto import ProximityAssetResponse, ProximityQueryRequest


def get_scene_frames(app: Container = Depends(get_container)) -> List[Dict[str, Any]]:
    """Every extracted object as a 3D frame (centre + size); bound assets carry their metadata."""
    return app.scene.frames()


def get_scene_summary(app: Container = Depends(get_container)) -> Dict[str, Any]:
    """Extraction statistics: algorithm, point count, objects per label, room, entry and target."""
    return app.scene.summary()


def get_scene_anchors(app: Container = Depends(get_container)) -> List[SceneAnchorRead]:
    """Anchors of all assets bound to extracted scene objects, with live health state."""
    return [SceneAnchorRead.model_validate(a) for a in app.scene.anchors()]


def query_proximity(payload: ProximityQueryRequest, app: Container = Depends(get_container)) -> List[ProximityAssetResponse]:
    """Assets whose scene object lies within radius_m of the avatar on the floor plane, nearest first."""
    return [ProximityAssetResponse.model_validate(p) for p in app.scene.proximity(payload.x, payload.z, payload.radius_m)]


def extract_scene_assets(app: Container = Depends(get_container)) -> Dict[str, Any]:
    """Re-run the extraction pipeline on the boiler-room point cloud and return all frames."""
    return app.scene.re_extract()


def get_boiler_room_ply(app: Container = Depends(get_container)) -> FileResponse:
    """Canonical (Y-up, floor at 0) point cloud for the Three.js PLYLoader."""
    with http_errors():
        path = app.scene.viewer_cloud()
    return FileResponse(path=str(path), media_type="application/octet-stream", filename=path.name)


def get_boiler_room_mesh(app: Container = Depends(get_container)) -> FileResponse:
    """Surface mesh reconstructed from the splat (rebuild offline with scripts/build_mesh.py)."""
    with http_errors():
        path = app.scene.viewer_mesh()
    return FileResponse(path=str(path), media_type="application/octet-stream", filename=path.name)
