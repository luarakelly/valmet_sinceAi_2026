"""Virtual cameras on walkable floor: evenly spread stations, several viewing directions each."""

from dataclasses import dataclass
import math
from typing import List, Tuple

import numpy as np

from infra.spatial.navigation import OccupancyGrid

VIEW_COUNT = 40
STATIONS = 8
YAWS_PER_STATION = 5
EYE_HEIGHT_M = 1.6
PITCH_DEG = -15.0
FOV_DEG = 70.0
LOOK_DISTANCE_M = 2.0
FULL_TURN_DEG = 360.0


@dataclass(frozen=True)
class CameraView:
    view_id: str
    eye: Tuple[float, float, float]
    target: Tuple[float, float, float]
    fov_deg: float


def plan_views(grid: OccupancyGrid, count: int = VIEW_COUNT) -> List[CameraView]:
    """Up to `count` views: STATIONS spread by farthest-point sampling, YAWS_PER_STATION each."""
    stations = _stations(grid)
    views: List[CameraView] = []
    for index, (x, z) in enumerate(stations):
        for yaw_index in range(YAWS_PER_STATION):
            yaw = (index * 0.5 + yaw_index) * FULL_TURN_DEG / YAWS_PER_STATION
            views.append(_view(f"V{index:02d}-{yaw_index}", x, z, yaw))
    return views[:count]


def _stations(grid: OccupancyGrid) -> List[Tuple[float, float]]:
    cells = np.argwhere(grid.reachable)
    if len(cells) == 0:
        return []
    points = np.array([grid.to_world((int(i), int(j))) for i, j in cells])
    centre = points.mean(axis=0)
    chosen = [int(np.argmin(np.linalg.norm(points - centre, axis=1)))]
    gap = np.linalg.norm(points - points[chosen[0]], axis=1)
    while len(chosen) < min(STATIONS, len(points)):
        chosen.append(int(np.argmax(gap)))
        gap = np.minimum(gap, np.linalg.norm(points - points[chosen[-1]], axis=1))
    return [(float(points[i][0]), float(points[i][1])) for i in chosen]


def _view(view_id: str, x: float, z: float, yaw_deg: float) -> CameraView:
    yaw = math.radians(yaw_deg)
    pitch = math.radians(PITCH_DEG)
    reach = LOOK_DISTANCE_M * math.cos(pitch)
    target = (x + math.sin(yaw) * reach, EYE_HEIGHT_M + LOOK_DISTANCE_M * math.sin(pitch), z + math.cos(yaw) * reach)
    return CameraView(view_id, (x, EYE_HEIGHT_M, z), target, FOV_DEG)
