"""Scene adapter: point cloud → semantic frames → asset bindings → navigation.

Implements the business `SceneEngine` port. Built once per process (≈1–2 s) by the
composition root (api/container.py) and shared by every service.
Coordinates are canonical: Y up, floor at y = 0 (see point_cloud.py).
"""

import base64
from dataclasses import dataclass, field
import logging
import math
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from infra.spatial.asset_mapping import Binding, Verified, bind_assets, choose_target
from infra.spatial.navigation import (
    ROBOT_RADIUS,
    STANDOFF_M,
    WALK_SPEED_M_S,
    Cell,
    OccupancyGrid,
    build_grid,
    nearest_free,
    plan_route,
    travel_distances,
    trim_to_standoff,
    walkable_layers,
)
from infra.spatial.point_cloud import PointCloud, VIEWER_MESH_PATH, VIEWER_PLY_PATH, load_scene_cloud
from infra.spatial.splat_export import ensure_viewer_splat
from infra.spatial.segmentation import Room, SceneObject, detect_room, extract_objects

logger = logging.getLogger("ask_your_factory.scene")

MAX_GEOMETRY_POINTS = 30000  # x-ray highlight payload stays < 360 KB

ALGORITHM = "Voxel connected components + recursive thin-link / sparse-plane splitting"


class RouteNotFound(Exception):
    """No collision-free route exists between the entry and the requested target."""


@dataclass(frozen=True)
class ScenePipelineResult:
    cloud: PointCloud
    room: Room
    objects: List[SceneObject]
    grid: OccupancyGrid
    entry: Tuple[float, float]
    bindings: Dict[str, Binding]
    target_asset_id: str
    seconds: float
    verified: Dict[str, Verified] = field(default_factory=dict)


class BoilerRoomScene:
    """SceneEngine adapter. `assets_provider` returns builder-pack assets (dicts with a "state")."""

    def __init__(
        self,
        assets_provider: Callable[[], List[Dict[str, Any]]],
        verification_provider: Optional[Callable[[], Dict[str, Dict[str, Any]]]] = None,
    ) -> None:
        self._assets_provider = assets_provider
        self._verification_provider = verification_provider or (lambda: {})
        self._build()

    def _build(self) -> None:
        self.result = run_pipeline(self._assets_provider(), self._verification_provider())
        self.frames = [self._frame(obj) for obj in self.result.objects]

    def rebuild(self) -> "BoilerRoomScene":
        """Re-run the pipeline from disk (e.g. after replacing the scan)."""
        self._build()
        return self

    def get_mesh_path(self) -> Path:
        return VIEWER_MESH_PATH

    def get_splat_path(self) -> Path:
        """Built from the raw scan on first use (≈10–30 s), then served from data/."""
        return ensure_viewer_splat()

    @property
    def target_asset_id(self) -> str:
        return self.result.target_asset_id

    def get_ply_path(self) -> Path:
        return VIEWER_PLY_PATH

    def get_semantic_frames(self) -> List[Dict[str, Any]]:
        return self.frames

    def summary(self) -> Dict[str, Any]:
        labels: Dict[str, int] = {}
        for frame in self.frames:
            labels[frame["label"]] = labels.get(frame["label"], 0) + 1
        room = self.result.room
        return {
            "algorithm": ALGORITHM,
            "source": self.result.cloud.source.name,
            "processed_points": len(self.result.cloud),
            "extracted_count": len(self.frames),
            "mapped_asset_count": len(self.result.bindings),
            "camera_verified_asset_count": sum(1 for b in self.result.bindings.values() if b.status == "camera_verified"),
            "verified_object_count": len(self.result.verified),
            "label_counts": labels,
            "room": {"x": [room.x_min, room.x_max], "z": [room.z_min, room.z_max], "ceiling": room.ceiling},
            "entry": {"x": self.result.entry[0], "y": 0.0, "z": self.result.entry[1]},
            "target_asset_id": self.target_asset_id,
            "processing_seconds": self.result.seconds,
        }

    def find_frame(self, identifier: str) -> Optional[Dict[str, Any]]:
        wanted = identifier.strip().lower()
        for frame in self.frames:
            keys = (frame["id"], frame["scene_id"], frame.get("tag") or "")
            if wanted in (k.lower() for k in keys):
                return frame
        return None

    def nearby(self, x: float, z: float, radius_m: float) -> List[Dict[str, Any]]:
        """Frames whose centre lies within radius_m of (x, z) on the floor plane, nearest first."""
        hits = []
        for frame in self.frames:
            distance = math.dist((x, z), (frame["pos"][0], frame["pos"][2]))
            if distance <= radius_m:
                hits.append({**frame, "distance_m": round(distance, 2)})
        return sorted(hits, key=lambda f: f["distance_m"])

    def get_navigation_path(
        self,
        target_id: Optional[str] = None,
        start: Optional[Tuple[float, float]] = None,
        goal: Optional[Tuple[float, float]] = None,
    ) -> Dict[str, Any]:
        grid = self.result.grid
        if goal is not None:
            # Floor point (click-to-walk): snap to the nearest walkable cell.
            goal_cell = nearest_free(grid, *goal)
            if goal_cell is None:
                raise RouteNotFound("POINT")
            gx, gz = grid.to_world(goal_cell)
            target = {"id": "POINT", "tag": "floor point", "pos": [round(gx, 3), 0.0, round(gz, 3)]}
        else:
            target = self.find_frame(target_id or self.target_asset_id)
            if target is None:
                raise KeyError(target_id)
            goal_cell = nearest_free(grid, target["pos"][0], target["pos"][2])

        origin = start or self.result.entry
        start_cell = nearest_free(grid, *origin)
        route = None
        if start_cell is not None and goal_cell is not None:
            route = plan_route(grid, start_cell, goal_cell)
        if route is None:
            raise RouteNotFound(target["id"])
        if goal is None and "size" in target:
            route = trim_to_standoff(grid, route, _footprint_distance(target))

        return {
            "target_id": target["id"],
            "target_tag": target["tag"],
            "target_pos": target["pos"],
            "waypoints": [{"x": x, "y": 0.0, "z": z} for x, z in route.waypoints],
            "total_distance_m": route.length_m,
            "estimated_walk_seconds": round(route.length_m / WALK_SPEED_M_S, 1),
            "collision_free": route.collision_free,
            "min_clearance_m": route.min_clearance_m,
            "robot_radius_m": ROBOT_RADIUS,
            "algorithm": "A* on inflated 2D occupancy grid + line-of-sight smoothing",
        }

    def get_object_geometry(self, identifier: str) -> Optional[bytes]:
        """The object's own points as little-endian float32 x, y, z triples; None if unknown."""
        frame = self.find_frame(identifier)
        if frame is None:
            return None
        obj = next(o for o in self.result.objects if o.object_id == frame["scene_id"])
        stride = max(1, -(-len(obj.points) // MAX_GEOMETRY_POINTS))
        return np.ascontiguousarray(obj.points[::stride], dtype="<f4").tobytes()

    def walkable_grid(self) -> Dict[str, Any]:
        """Occupancy grid for the viewer (walkable overlay + camera collision), layers as base64 bytes."""
        layers = walkable_layers(self.result.grid)
        for key in ("reachable", "blocked"):
            layers[key] = base64.b64encode(layers[key].tobytes(order="C")).decode("ascii")
        return layers

    def _seen_as(self, obj: SceneObject) -> Optional[Dict[str, Any]]:
        """What the camera check said this object is, if it has been looked at."""
        seen = self.result.verified.get(obj.object_id)
        if seen is None:
            return None
        return {"category": seen.category, "confidence": seen.confidence, "features": seen.features}

    def _frame(self, obj: SceneObject) -> Dict[str, Any]:
        binding = self.result.bindings.get(obj.object_id)
        frame: Dict[str, Any] = {
            "id": obj.object_id,
            "scene_id": obj.object_id,
            "tag": obj.object_id,
            "label": obj.label,
            "class": obj.label,
            "pos": list(obj.center),
            "size": list(obj.size),
            "point_count": obj.point_count,
            "asset_id": None,
            "mapped_asset": None,
            "mapping_confidence": None,
            "mapping_status": None,
            "mapping_evidence": None,
            "seen_as": self._seen_as(obj),
            "state": None,
            "health": None,
            "issue_code": None,
            "is_target": False,
        }
        if binding is None:
            return frame

        asset = binding.asset
        state = asset.get("state") or {}
        frame.update({
            "id": asset["asset_id"],
            "tag": asset.get("tag"),
            "class": asset.get("asset_class"),
            "asset_id": asset["asset_id"],
            "mapped_asset": {
                "asset_id": asset["asset_id"],
                "tag": asset.get("tag"),
                "asset_class": asset.get("asset_class"),
                "area_id": asset.get("area_id"),
                "area_name": asset.get("area_name"),
                "criticality": asset.get("criticality"),
            },
            "mapping_confidence": binding.confidence,
            "mapping_status": binding.status,
            "mapping_evidence": binding.evidence,
            "state": state.get("condition_state"),
            "health": state.get("health_score"),
            "issue_code": state.get("issue_code"),
            "is_target": asset["asset_id"] == self.target_asset_id,
        })
        return frame


def run_pipeline(assets: List[Dict[str, Any]], verification: Optional[Dict[str, Dict[str, Any]]] = None) -> ScenePipelineResult:
    started = time.perf_counter()
    cloud = load_scene_cloud()
    room = detect_room(cloud)
    objects = extract_objects(cloud, room)
    grid = build_grid(cloud, room)

    entry_cell = _walkway_end(grid, room)
    entry = grid.to_world(entry_cell)

    travel = travel_distances(grid, entry_cell)
    reach: Dict[str, float] = {}
    walk: Dict[str, float] = {}
    for obj in objects:
        stand = nearest_free(grid, obj.center[0], obj.center[2])
        reach[obj.object_id] = math.dist((obj.center[0], obj.center[2]), grid.to_world(stand))
        walk[obj.object_id] = float(travel[stand])

    target = choose_target(assets)
    verified = _verified_objects(verification or {}, objects)
    bindings = bind_assets(objects, assets, target["asset_id"], reach, walk, verified)

    seconds = round(time.perf_counter() - started, 2)
    logger.info("Scene pipeline: %d points → %d objects (%d camera-verified), %d assets bound in %.2fs", len(cloud), len(objects), len(verified), len(bindings), seconds)
    return ScenePipelineResult(cloud, room, objects, grid, entry, bindings, target["asset_id"], seconds, verified)


STALE_VERIFICATION_M = 0.15


def _verified_objects(records: Dict[str, Dict[str, Any]], objects: List[SceneObject]) -> Dict[str, Verified]:
    """Stored camera verifications that still describe the same object (same id, same place)."""
    by_id = {obj.object_id: obj for obj in objects}
    verified: Dict[str, Verified] = {}
    for object_id, record in records.items():
        obj = by_id.get(object_id)
        if obj is None:
            continue
        center = record.get("center")
        if center and math.dist(center, obj.center) > STALE_VERIFICATION_M:
            continue  # the scan or the extraction changed: this verdict is about something else now
        verified[object_id] = Verified(
            category=str(record.get("category", "unknown")),
            asset_class=record.get("asset_class"),
            confidence=float(record.get("confidence", 0.0)),
            features=str(record.get("visible_features", "")),
        )
    return verified


def _walkway_end(grid: OccupancyGrid, room: Room) -> Cell:
    """Entry point: the walkway extremity found by a double sweep from the room's west side.

    The scan has no door annotation, so the robot starts at one end of the longest walk.
    """
    seed = nearest_free(grid, room.x_min, (room.z_min + room.z_max) / 2)
    if seed is None:
        raise RuntimeError("Occupancy grid has no free floor space")
    distances = travel_distances(grid, seed)
    distances[~np.isfinite(distances)] = -1.0
    i, j = np.unravel_index(int(np.argmax(distances)), distances.shape)
    return int(i), int(j)


def _footprint_distance(frame: Dict[str, Any]) -> Callable[[float, float], float]:
    """Floor distance from a point to the frame's box footprint (0 inside it)."""
    cx, _, cz = frame["pos"]
    half_w, half_d = frame["size"][0] / 2, frame["size"][2] / 2

    def distance(x: float, z: float) -> float:
        return math.hypot(max(abs(x - cx) - half_w, 0.0), max(abs(z - cz) - half_d, 0.0))

    return distance
