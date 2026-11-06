"""Obstacle-aware navigation on a 2D occupancy grid sliced from the canonical cloud.

- Obstacles: cells with enough points between ankle height and robot height (clipping walls,
  equipment and low piping; overhead racks above the robot stay passable).
- Free space: inside the room footprint, not an obstacle, and at least ROBOT_RADIUS from one
  (Euclidean distance transform = configuration-space inflation).
- Route: 8-connected A*, then line-of-sight shortcutting. Every final segment is re-sampled and
  its true clearance reported, so `collision_free` is measured rather than asserted.
"""

from dataclasses import dataclass
import heapq
import math
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import ndimage

from app.metaverse.point_cloud import PointCloud
from app.metaverse.segmentation import Room

CELL = 0.08
ANKLE_HEIGHT = 0.1
ROBOT_HEIGHT = 1.2
ROBOT_RADIUS = 0.22
MIN_OBSTACLE_POINTS = 3
SEGMENT_SAMPLE_STEP = 0.02
WALK_SPEED_M_S = 0.8

Cell = Tuple[int, int]
NEIGHBOURS_8 = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]


@dataclass(frozen=True)
class OccupancyGrid:
    """Cell (i, j) covers x = x_min + i·CELL, z = z_min + j·CELL.

    clearance: metres to the nearest obstacle.
    reachable: free cells in the largest connected free region (isolated pockets are unusable).
    """

    x_min: float
    z_min: float
    clearance: np.ndarray
    reachable: np.ndarray

    def to_cell(self, x: float, z: float) -> Cell:
        nx, nz = self.clearance.shape
        i = int(np.clip((x - self.x_min) / CELL, 0, nx - 1))
        j = int(np.clip((z - self.z_min) / CELL, 0, nz - 1))
        return i, j

    def to_world(self, cell: Cell) -> Tuple[float, float]:
        return self.x_min + (cell[0] + 0.5) * CELL, self.z_min + (cell[1] + 0.5) * CELL

    def clearance_at(self, x: float, z: float) -> float:
        return float(self.clearance[self.to_cell(x, z)])


@dataclass(frozen=True)
class Route:
    waypoints: List[Tuple[float, float]]
    length_m: float
    min_clearance_m: float
    collision_free: bool


def build_grid(cloud: PointCloud, room: Room) -> OccupancyGrid:
    nx = int(math.ceil((room.x_max - room.x_min) / CELL))
    nz = int(math.ceil((room.z_max - room.z_min) / CELL))
    xyz = cloud.xyz
    body = (xyz[:, 1] > ANKLE_HEIGHT) & (xyz[:, 1] < ROBOT_HEIGHT)
    i = np.floor((xyz[body, 0] - room.x_min) / CELL).astype(int)
    j = np.floor((xyz[body, 2] - room.z_min) / CELL).astype(int)
    inside = (i >= 0) & (i < nx) & (j >= 0) & (j < nz)

    counts = np.zeros((nx, nz), dtype=np.int32)
    np.add.at(counts, (i[inside], j[inside]), 1)
    obstacle = ndimage.binary_closing(counts >= MIN_OBSTACLE_POINTS)
    obstacle = np.pad(obstacle, 1, constant_values=True)  # room walls bound the grid
    clearance = ndimage.distance_transform_edt(~obstacle)[1:-1, 1:-1] * CELL

    regions, count = ndimage.label(clearance >= ROBOT_RADIUS)
    if count == 0:
        reachable = np.zeros_like(clearance, dtype=bool)
    else:
        sizes = np.bincount(regions.ravel())[1:]
        reachable = regions == int(np.argmax(sizes)) + 1
    return OccupancyGrid(x_min=room.x_min, z_min=room.z_min, clearance=clearance, reachable=reachable)


def nearest_free(grid: OccupancyGrid, x: float, z: float) -> Optional[Cell]:
    """Closest reachable cell to a world point (e.g. a standing spot in front of a machine)."""
    free = np.argwhere(grid.reachable)
    if len(free) == 0:
        return None
    target = np.array(grid.to_cell(x, z))
    best = free[np.argmin(((free - target) ** 2).sum(axis=1))]
    return int(best[0]), int(best[1])


def travel_distances(grid: OccupancyGrid, start: Cell) -> np.ndarray:
    """Walking distance (metres) from start to every reachable cell; inf elsewhere (Dijkstra)."""
    distance = np.full(grid.reachable.shape, math.inf)
    distance[start] = 0.0
    heap = [(0.0, start)]
    while heap:
        travelled, current = heapq.heappop(heap)
        if travelled > distance[current]:
            continue
        for nxt, step in _neighbours(grid.reachable, current):
            candidate = travelled + step * CELL
            if candidate < distance[nxt]:
                distance[nxt] = candidate
                heapq.heappush(heap, (candidate, nxt))
    return distance


def plan_route(grid: OccupancyGrid, start: Cell, goal: Cell) -> Optional[Route]:
    cells = _astar(grid.reachable, start, goal)
    if cells is None:
        return None
    corners = _shortcut(grid.reachable, cells)
    waypoints = [grid.to_world(c) for c in corners]
    length = sum(math.dist(a, b) for a, b in zip(waypoints, waypoints[1:]))
    min_clearance = _min_clearance(grid, waypoints)
    return Route(
        waypoints=[(round(x, 3), round(z, 3)) for x, z in waypoints],
        length_m=round(length, 2),
        min_clearance_m=round(min_clearance, 3),
        collision_free=min_clearance >= ROBOT_RADIUS - CELL / 2,
    )


def _neighbours(free: np.ndarray, cell: Cell):
    """8-connected free neighbours with step length in cells; diagonals may not cut corners."""
    nx, nz = free.shape
    for di, dj in NEIGHBOURS_8:
        nxt = (cell[0] + di, cell[1] + dj)
        if not (0 <= nxt[0] < nx and 0 <= nxt[1] < nz and free[nxt]):
            continue
        if di and dj and not (free[cell[0] + di, cell[1]] and free[cell[0], cell[1] + dj]):
            continue
        yield nxt, math.hypot(di, dj)


def _astar(free: np.ndarray, start: Cell, goal: Cell) -> Optional[List[Cell]]:
    open_heap = [(0.0, start)]
    cost: Dict[Cell, float] = {start: 0.0}
    parent: Dict[Cell, Cell] = {}
    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current == goal:
            path = [current]
            while current in parent:
                current = parent[current]
                path.append(current)
            return path[::-1]
        for nxt, length in _neighbours(free, current):
            step = cost[current] + length
            if step < cost.get(nxt, math.inf):
                cost[nxt] = step
                parent[nxt] = current
                heapq.heappush(open_heap, (step + math.dist(nxt, goal), nxt))
    return None


def _line_is_free(free: np.ndarray, a: Cell, b: Cell) -> bool:
    steps = max(abs(b[0] - a[0]), abs(b[1] - a[1])) * 3 + 1
    for t in np.linspace(0.0, 1.0, steps):
        i = int(round(a[0] + (b[0] - a[0]) * t))
        j = int(round(a[1] + (b[1] - a[1]) * t))
        if not free[i, j]:
            return False
    return True


def _shortcut(free: np.ndarray, cells: List[Cell]) -> List[Cell]:
    """Greedy string-pulling: jump to the furthest cell still in line of sight."""
    corners = [cells[0]]
    index = 0
    while index < len(cells) - 1:
        furthest = index + 1
        for candidate in range(len(cells) - 1, index + 1, -1):
            if _line_is_free(free, cells[index], cells[candidate]):
                furthest = candidate
                break
        corners.append(cells[furthest])
        index = furthest
    return corners


def _min_clearance(grid: OccupancyGrid, waypoints: List[Tuple[float, float]]) -> float:
    lowest = math.inf
    for (x0, z0), (x1, z1) in zip(waypoints, waypoints[1:]):
        samples = max(2, int(math.dist((x0, z0), (x1, z1)) / SEGMENT_SAMPLE_STEP))
        for t in np.linspace(0.0, 1.0, samples):
            lowest = min(lowest, grid.clearance_at(x0 + (x1 - x0) * t, z0 + (z1 - z0) * t))
    if lowest == math.inf:
        return grid.clearance_at(*waypoints[0])
    return lowest
