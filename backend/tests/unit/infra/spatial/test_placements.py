"""Placements: a 2D box in a rendered view becomes a 3D box on the nearest scan surface."""

from pathlib import Path

import numpy as np

from infra.spatial.asset_mapping import CONFIRMED, PLACEMENT_PROPOSED
from infra.spatial.placements import PLACED_LABEL, drop_covered, lift_box, placed_objects
from infra.spatial.point_cloud import PointCloud
from infra.spatial.scene_pipeline import _bind
from infra.spatial.segmentation import SceneObject

FOV_DEGREES = 60.0
NEAR, FAR = 0.1, 100.0
CUBE_DEPTH = 5.0
WALL_DEPTH = 8.0
CENTER_BOX = [0.4, 0.4, 0.6, 0.6]
SIZE_TOLERANCE = 0.1


def camera_at_origin_looking_down_minus_z() -> list:
    """three.js style view-projection (identity view), flattened column-major like Matrix4.elements."""
    f = 1.0 / np.tan(np.radians(FOV_DEGREES) / 2.0)
    projection = np.array([
        [f, 0.0, 0.0, 0.0],
        [0.0, f, 0.0, 0.0],
        [0.0, 0.0, (FAR + NEAR) / (NEAR - FAR), 2.0 * FAR * NEAR / (NEAR - FAR)],
        [0.0, 0.0, -1.0, 0.0],
    ])
    return projection.T.flatten().tolist()


def cube(center_z: float, side: float = 1.0, count: int = 4000) -> np.ndarray:
    rng = np.random.default_rng(1)
    points = rng.uniform(-side / 2.0, side / 2.0, size=(count, 3))
    points[:, 2] += center_z
    return points


def wall(depth: float, count: int = 4000) -> np.ndarray:
    rng = np.random.default_rng(2)
    points = rng.uniform(-3.0, 3.0, size=(count, 3))
    points[:, 2] = depth
    return points


def scene_object(object_id: str, center, size) -> SceneObject:
    return SceneObject(object_id=object_id, label="VALVE_ASSEMBLY", center=center, size=size, point_count=10, color=(0.5, 0.5, 0.5))


def test_lifted_box_fits_the_object_in_front_not_the_wall_behind_it():
    xyz = np.vstack([cube(-CUBE_DEPTH), wall(-WALL_DEPTH)])
    lifted = lift_box(xyz, camera_at_origin_looking_down_minus_z(), CENTER_BOX)
    assert lifted is not None
    assert np.allclose(lifted.size, (1.0, 1.0, 1.0), atol=SIZE_TOLERANCE + 0.05)
    assert abs(lifted.center[2] + CUBE_DEPTH) < SIZE_TOLERANCE


def test_a_box_over_empty_space_lifts_to_nothing():
    xyz = cube(-CUBE_DEPTH)
    assert lift_box(xyz, camera_at_origin_looking_down_minus_z(), [0.0, 0.0, 0.1, 0.1]) is None


def test_points_behind_the_camera_are_ignored():
    xyz = cube(CUBE_DEPTH)
    assert lift_box(xyz, camera_at_origin_looking_down_minus_z(), CENTER_BOX) is None


def test_a_placement_replaces_the_extracted_objects_it_covers():
    placed = scene_object("PLACED-ASSET-001", (0.0, 0.5, 0.0), (1.0, 1.0, 1.0))
    inside = scene_object("OBJ-001", (0.0, 0.5, 0.0), (0.4, 0.4, 0.4))
    outside = scene_object("OBJ-002", (3.0, 0.5, 0.0), (0.4, 0.4, 0.4))
    assert drop_covered([inside, outside], [placed]) == [outside]


def test_placed_objects_skip_unknown_assets_and_malformed_boxes():
    rng = np.random.default_rng(3)
    cloud = PointCloud(xyz=rng.uniform(-1.0, 1.0, size=(500, 3)), rgb=np.full((500, 3), 0.25), source=Path("scan.ply"))
    records = {
        "ASSET-001": {"center": [0.0, 0.0, 0.0], "size": [1.0, 1.0, 1.0]},
        "ASSET-GONE": {"center": [0.0, 0.0, 0.0], "size": [1.0, 1.0, 1.0]},
        "ASSET-002": {"center": [0.0, 0.0], "size": [1.0, 1.0, 1.0]},
        "ASSET-003": {"center": [0.0, 0.0, 0.0], "size": [1.0, 0.0, 1.0]},
    }
    placed = placed_objects(cloud, records, {"ASSET-001", "ASSET-002", "ASSET-003"})
    assert list(placed) == ["ASSET-001"]
    assert placed["ASSET-001"].label == PLACED_LABEL
    assert placed["ASSET-001"].point_count > 0


def test_a_confirmed_asset_keeps_its_object_and_the_guesser_never_touches_it():
    asset = {"asset_id": "ASSET-001", "tag": "P-001", "asset_class": "PROCESS_PUMP", "state": {"health_score": 90}}
    other = {"asset_id": "ASSET-002", "tag": "P-002", "asset_class": "PROCESS_PUMP", "state": {"health_score": 80}}
    placed = {"ASSET-001": scene_object("PLACED-ASSET-001", (0.0, 0.5, 0.0), (1.0, 1.0, 1.0))}
    guessable = scene_object("OBJ-001", (3.0, 0.5, 0.0), (1.0, 1.0, 1.0))
    objects = [placed["ASSET-001"], guessable]
    reach = {obj.object_id: 0.0 for obj in objects}

    records = {"ASSET-001": {"center": [0.0, 0.5, 0.0], "size": [1.0, 1.0, 1.0], "status": "confirmed"}}

    bindings = _bind(objects, [asset, other], placed, records, "ASSET-001", reach, dict(reach), {})

    assert bindings["PLACED-ASSET-001"].status == CONFIRMED
    assert bindings["PLACED-ASSET-001"].asset["asset_id"] == "ASSET-001"
    assert bindings["OBJ-001"].asset["asset_id"] == "ASSET-002"


def test_a_proposed_placement_binds_below_certainty():
    asset = {"asset_id": "ASSET-001", "tag": "P-001", "asset_class": "PROCESS_PUMP", "state": {"health_score": 90}}
    placed = {"ASSET-001": scene_object("PLACED-ASSET-001", (0.0, 0.5, 0.0), (1.0, 1.0, 1.0))}
    objects = [placed["ASSET-001"]]
    reach = {"PLACED-ASSET-001": 0.0}
    records = {"ASSET-001": {"center": [0.0, 0.5, 0.0], "size": [1.0, 1.0, 1.0], "status": "proposed"}}

    bindings = _bind(objects, [asset], placed, records, "ASSET-001", reach, dict(reach), {})

    assert bindings["PLACED-ASSET-001"].status == PLACEMENT_PROPOSED
    assert bindings["PLACED-ASSET-001"].confidence < 1.0
