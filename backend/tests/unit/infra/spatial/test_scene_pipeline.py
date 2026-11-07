"""Scene pipeline tests: canonical frame, extraction density, bindings and navigation guarantees."""

import base64
import math

import numpy as np

from functools import lru_cache

from infra.importers.workbook.dataset import get_dataset
from infra.spatial.navigation import CELL, ROBOT_RADIUS, STANDOFF_M, OccupancyGrid, plan_route, walkable_layers
from infra.spatial.scene_pipeline import BoilerRoomScene
from infra.spatial.segmentation import classify


@lru_cache(maxsize=1)
def get_scene() -> BoilerRoomScene:
    return BoilerRoomScene(get_dataset().get_assets)


def _grid_with_wall(gap_rows: range) -> OccupancyGrid:
    """10 m × 4 m room, wall at x = 5 m with a doorway over gap_rows."""
    obstacle = np.zeros((125, 50), dtype=bool)
    obstacle[62, :] = True
    obstacle[62, gap_rows] = False
    from scipy import ndimage

    padded = np.pad(obstacle, 1, constant_values=True)
    clearance = ndimage.distance_transform_edt(~padded)[1:-1, 1:-1] * CELL
    return OccupancyGrid(x_min=0.0, z_min=0.0, clearance=clearance, reachable=clearance >= ROBOT_RADIUS)


def test_route_passes_through_doorway_without_touching_wall():
    grid = _grid_with_wall(range(30, 45))
    route = plan_route(grid, grid.to_cell(1.0, 0.5), grid.to_cell(9.0, 0.5))
    assert route is not None
    assert route.collision_free
    assert route.min_clearance_m >= ROBOT_RADIUS - CELL / 2
    crossing = [(a, b) for a, b in zip(route.waypoints, route.waypoints[1:]) if (a[0] - 5.0) * (b[0] - 5.0) < 0]
    assert len(crossing) == 1
    (x0, z0), (x1, z1) = crossing[0]
    z_at_wall = z0 + (z1 - z0) * (5.0 - x0) / (x1 - x0)
    assert 30 * CELL <= z_at_wall <= 45 * CELL


def test_route_is_none_when_wall_is_closed():
    grid = _grid_with_wall(range(0))
    assert plan_route(grid, grid.to_cell(1.0, 2.0), grid.to_cell(9.0, 2.0)) is None


def test_classify_uses_geometry_and_colour():
    assert classify(np.array([0, 2.0, 0]), np.array([2.0, 0.15, 0.15]), np.full(3, 0.5)) == "OVERHEAD_PIPE_RUN"
    assert classify(np.array([0, 0.3, 0]), np.array([0.6, 0.6, 0.5]), np.full(3, 0.5)) == "FLOOR_MOUNTED_MACHINE"
    assert classify(np.array([0, 0.4, 0]), np.array([0.2, 0.4, 0.2]), np.array([0.8, 0.2, 0.2])) == "FIRE_SAFETY_EQUIPMENT"


def test_cloud_is_canonical_y_up_with_floor_at_zero():
    cloud = get_scene().result.cloud
    heights = cloud.xyz[:, 1]
    counts, edges = np.histogram(heights[heights < 1.0], bins=np.arange(-0.5, 1.0, 0.02))
    floor = edges[np.argmax(counts)]
    assert abs(floor) <= 0.04
    assert np.percentile(heights, 99) > 1.5  # equipment and pipe racks stand above the floor


def test_extraction_is_dense_and_binds_every_asset():
    scene = get_scene()
    frames = scene.get_semantic_frames()
    bound = [f for f in frames if f["asset_id"]]
    assert len(frames) >= 100
    assert len({f["asset_id"] for f in bound}) == 30
    assert sum(f["is_target"] for f in frames) == 1
    for frame in frames:
        assert all(s > 0 for s in frame["size"])
        assert frame["pos"][1] - frame["size"][1] / 2 >= 0.0  # nothing below the floor


def test_route_to_every_asset_is_collision_free():
    scene = get_scene()
    for frame in scene.get_semantic_frames():
        if not frame["asset_id"]:
            continue
        route = scene.get_navigation_path(frame["asset_id"])
        assert route["collision_free"], frame["asset_id"]
        last = route["waypoints"][-1]
        # Stops at an inspection distance from the asset's footprint: close, but not touching.
        gap = math.hypot(max(abs(last["x"] - frame["pos"][0]) - frame["size"][0] / 2, 0),
                         max(abs(last["z"] - frame["pos"][2]) - frame["size"][2] / 2, 0))
        assert gap <= STANDOFF_M + 0.25, (frame["asset_id"], gap)
        assert gap >= min(STANDOFF_M, 0.3) - CELL or len(route["waypoints"]) == 1, (frame["asset_id"], gap)


def test_walkable_grid_matches_the_route_grid():
    scene = get_scene()
    layers = walkable_layers(scene.result.grid)
    encoded = scene.walkable_grid()
    assert len(base64.b64decode(encoded["reachable"])) == layers["nx"] * layers["nz"]
    assert layers["reachable"].shape == (layers["nx"], layers["nz"])
    assert layers["reachable"].sum() > 0
    # Nowhere walkable is also an obstacle.
    assert not (layers["reachable"].astype(bool) & layers["blocked"].astype(bool)).any()


def test_route_to_a_floor_point_snaps_to_walkable_space():
    scene = get_scene()
    grid = scene.result.grid
    target = next(f for f in scene.get_semantic_frames() if f["asset_id"])
    # A point inside an object is not walkable: the goal snaps to the nearest free cell.
    route = scene.get_navigation_path(goal=(target["pos"][0], target["pos"][2]))
    assert route["target_id"] == "POINT"
    assert route["collision_free"]
    gx, _, gz = route["target_pos"]
    assert grid.clearance_at(gx, gz) >= ROBOT_RADIUS - CELL
    last = route["waypoints"][-1]
    assert math.dist((last["x"], last["z"]), (gx, gz)) <= CELL * 1.5

    # Starting from where the robot stands now (not the entry) also works.
    first = scene.get_navigation_path(target["asset_id"])["waypoints"][-1]
    again = scene.get_navigation_path(start=(first["x"], first["z"]), goal=(gx, gz))
    assert again["collision_free"]


def test_object_geometry_is_the_objects_own_points_inside_its_frame():
    scene = get_scene()
    frame = next(f for f in scene.get_semantic_frames() if f["asset_id"])
    points = np.frombuffer(scene.get_object_geometry(frame["tag"]), dtype="<f4").reshape(-1, 3)
    assert len(points) > 0
    low = np.array(frame["pos"]) - np.array(frame["size"]) / 2 - 1e-3
    high = np.array(frame["pos"]) + np.array(frame["size"]) / 2 + 1e-3
    assert ((points >= low) & (points <= high)).all()
    assert scene.get_object_geometry("NO-SUCH-OBJECT") is None
