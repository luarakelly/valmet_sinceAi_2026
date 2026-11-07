import numpy as np

from infra.labeling.segmenter import MAX_MASK_FRACTION, keep_detections
from infra.labeling.semantic_objects import (
    SemanticObject,
    asset_class_of,
    merge_semantic,
    points_in_box,
    read_semantic_objects,
    to_scene_object,
    write_semantic_objects,
)
from infra.spatial.segmentation import SceneObject

SIZE = 100


def mask_of(rows, cols):
    mask = np.zeros((SIZE, SIZE), dtype=bool)
    mask[rows, cols] = True
    return mask


def test_wall_sized_mask_is_dropped_and_object_sized_kept():
    wall = mask_of(slice(0, 80), slice(0, 80))
    assert wall.mean() > MAX_MASK_FRACTION
    valve = mask_of(slice(40, 60), slice(40, 60))
    kept = keep_detections(["pipe", "valve", "banana"], [0.9, 0.8, 0.9], [wall, valve, valve])
    assert [d.term.label for d in kept] == ["VALVE"]


def semantic(object_id="SEM-1", label="PUMP", center=(1.0, 0.5, 1.0), yaw=0.0):
    return SemanticObject(object_id, label, asset_class_of(label), center, (1.0, 1.0, 0.5), yaw, 500, 0.8, 3)


def test_round_trip_and_missing_or_malformed_file(tmp_path):
    path = tmp_path / "semantic_objects.json"
    assert read_semantic_objects(path) == []
    write_semantic_objects(path, [semantic()])
    assert read_semantic_objects(path) == [semantic()]
    path.write_text("{not json")
    assert read_semantic_objects(path) == []
    path.write_text('{"objects": [{"label": "x"}]}')
    assert read_semantic_objects(path) == []


def test_yawed_box_membership():
    box = to_scene_object(semantic(yaw=np.pi / 2))  # long x-axis now points along +z
    inside = np.array([[1.0, 0.5, 1.45]])
    outside = np.array([[1.45, 0.5, 1.0]])
    assert points_in_box(inside, box, margin=0.0).all()
    assert not points_in_box(outside, box, margin=0.0).any()


def geometric(object_id, center):
    points = np.random.default_rng(1).normal(center, 0.05, (200, 3)).astype(np.float32)
    return SceneObject(object_id, "FLOOR_MOUNTED_MACHINE", tuple(center), (0.3, 0.3, 0.3), 200, (0.5, 0.5, 0.5), points=points)


def test_semantic_replaces_covered_geometry_and_carries_asset_class():
    near, far = geometric("OBJ-1", (1.0, 0.5, 1.0)), geometric("OBJ-2", (5.0, 0.5, 5.0))
    merged, verified = merge_semantic([near, far], [semantic()])
    assert [o.object_id for o in merged] == ["OBJ-2", "SEM-1"]
    assert verified["SEM-1"].asset_class == "PROCESS_PUMP"
    assert merged[-1].label == "PUMP"


def test_unmapped_labels_have_no_asset_class():
    assert asset_class_of("CRATE") is None
    assert asset_class_of("NOPE") is None


def test_footprint_distance_follows_the_box_yaw():
    from infra.spatial.scene_pipeline import _footprint_distance

    frame = {"pos": [0.0, 0.5, 0.0], "size": [2.0, 1.0, 0.2], "yaw": np.pi / 2}  # long side now along z
    distance = _footprint_distance(frame)
    assert distance(0.0, 0.9) == 0.0
    assert abs(distance(0.5, 0.0) - 0.4) < 1e-9


def test_labeling_service_saves_views_and_rejects_bad_base64(tmp_path):
    import base64

    import pytest

    from business.errors import InvalidRequestError
    from business.services.labeling_service import LabelingService
    from infra.labeling.view_store import FileViewStore

    class FakeScene:
        def labeling_views(self):
            return [{"view_id": "V00-0"}]

    service = LabelingService(FakeScene(), FileViewStore(tmp_path))
    assert service.plan() == {"views": [{"view_id": "V00-0"}], "captured": []}
    saved = service.save_view("V00-0", base64.b64encode(b"jpegbytes").decode(), [0.0] * 16, 64, 48)
    assert saved["captured_count"] == 1
    assert (tmp_path / "V00-0.jpg").read_bytes() == b"jpegbytes"
    with pytest.raises(InvalidRequestError):
        service.save_view("V00-1", "not base64!!", [0.0] * 16, 64, 48)
    with pytest.raises(ValueError):
        FileViewStore(tmp_path).save("../evil", b"x", {})
