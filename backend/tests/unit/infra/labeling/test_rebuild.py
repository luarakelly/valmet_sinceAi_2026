import json

import numpy as np

from infra.labeling.annotations import Report, load_annotations
from infra.labeling.rebuild import rebuild_objects
from infra.labeling.semantic_objects import SemanticObject
from infra.labeling.view_quality import view_problem
from infra.spatial.segmentation import Room
from tests.unit.infra.spatial.test_placements import camera_at_origin_looking_down_minus_z

ROOM = Room(-10.0, 10.0, -10.0, 10.0, 3.0)
VP = camera_at_origin_looking_down_minus_z()
CENTRE_BOX = [0.45, 0.45, 0.55, 0.55]


def scene_points():
    rng = np.random.default_rng(0)
    crate = (rng.random((20000, 3)) - 0.5) * 0.6 + np.array([0.0, 0.0, -4.0])
    wall = np.column_stack([rng.uniform(-6, 6, 60000), rng.uniform(-6, 6, 60000), np.full(60000, -9.0)])
    return np.vstack([crate, wall])


def write(path, views):
    path.write_text(json.dumps({"version": 1, "views": views}))
    return path


def test_two_views_of_one_crate_become_one_object_and_rebuild_is_deterministic(tmp_path):
    path = write(tmp_path / "a.json", {"A": [{"label": "CRATE", "box": CENTRE_BOX}], "B": [{"label": "CRATE", "box": CENTRE_BOX}]})
    projections = {"A": VP, "B": VP}
    first = rebuild_objects(scene_points(), ROOM, projections, path, [])
    second = rebuild_objects(scene_points(), ROOM, projections, path, [])
    assert [o.label for o in first.objects] == ["CRATE"]
    assert first.objects[0].object_id == "SEM-CRATE-01"
    assert first.objects[0].view_count == 2
    assert first.objects == second.objects


def test_bad_input_is_reported_not_raised(tmp_path):
    path = write(tmp_path / "a.json", {
        "A": [
            {"label": "UNICORN", "box": CENTRE_BOX},
            {"label": "CRATE", "box": [0.6, 0.6, 0.4, 0.4]},
            {"label": "CRATE"},
            {"label": "CRATE", "box": [0.0, 0.0, 0.4, 0.4]},
        ],
        "GHOST": [{"label": "CRATE", "box": CENTRE_BOX}],
    })
    result = rebuild_objects(scene_points(), ROOM, {"A": VP}, path, [])
    assert result.objects == []
    text = " | ".join(result.issues)
    for expected in ("unknown label", "inverted", "needs a label", "no camera", "implausible size"):
        assert expected in text


def test_missing_or_corrupt_annotation_file(tmp_path):
    report = Report()
    assert load_annotations(tmp_path / "nope.json", report) == []
    (tmp_path / "bad.json").write_text("{oops")
    assert load_annotations(tmp_path / "bad.json", report) == []
    assert len(report.issues) == 2


def test_model_objects_add_but_never_duplicate_hand_drawn_ones(tmp_path):
    path = write(tmp_path / "a.json", {"A": [{"label": "CRATE", "box": CENTRE_BOX}]})
    duplicate = SemanticObject("M-1", "CRATE", None, (0.0, 0.0, -4.0), (0.6, 0.6, 0.6), 0.0, 100, 0.9, 3)
    extra = SemanticObject("M-2", "PIPE", None, (5.0, 1.0, 5.0), (2.0, 0.2, 0.2), 0.0, 100, 0.9, 3)
    outside = SemanticObject("M-3", "PIPE", None, (50.0, 1.0, 5.0), (2.0, 0.2, 0.2), 0.0, 100, 0.9, 3)
    result = rebuild_objects(scene_points(), ROOM, {"A": VP}, path, [duplicate, extra, outside])
    assert sorted(o.label for o in result.objects) == ["CRATE", "PIPE"]
    assert any("outside the room" in issue for issue in result.issues)


def test_black_and_smeared_views_are_rejected():
    assert view_problem(np.zeros((40, 40, 3), dtype=np.uint8)) == "too dark"
    assert view_problem(np.full((40, 40, 3), 120, dtype=np.uint8)) == "too blurry"
    noisy = np.random.default_rng(0).integers(0, 255, (40, 40, 3)).astype(np.uint8)
    assert view_problem(noisy) == ""


def test_write_is_atomic_and_leaves_no_temporary_file(tmp_path):
    from infra.labeling.semantic_objects import read_semantic_objects, write_semantic_objects

    path = tmp_path / "semantic_objects.json"
    write_semantic_objects(path, [SemanticObject("S", "PUMP", "PROCESS_PUMP", (0, 0, 0), (1, 1, 1), 0.0, 5, 0.5, 1)])
    assert [p.name for p in tmp_path.iterdir()] == ["semantic_objects.json"]
    assert len(read_semantic_objects(path)) == 1


def test_boxes_are_trimmed_to_floor_and_ceiling():
    from infra.labeling.rebuild import _clamped_to_height

    low = SemanticObject("S", "CRATE", None, (0, 0.45, 0), (1, 1.0, 1), 0.0, 5, 0.5, 1)
    tall = SemanticObject("S", "PIPE", None, (0, 2.9, 0), (1, 0.6, 1), 0.0, 5, 0.5, 1)
    trimmed = _clamped_to_height(low, ROOM)
    assert trimmed.center[1] - trimmed.size[1] / 2 == 0.0
    assert _clamped_to_height(tall, ROOM).center[1] + _clamped_to_height(tall, ROOM).size[1] / 2 == 3.0


def test_box_grows_to_the_whole_item_from_its_fragments(tmp_path):
    """A lifted front slab is 0.6 m wide; two fragments of the same crate make it 1.0 m."""
    from infra.spatial.segmentation import SceneObject

    rng = np.random.default_rng(1)
    left = ((rng.random((6000, 3)) - 0.5) * np.array([0.5, 0.6, 0.6]) + np.array([-0.25, 0.3, -4.0])).astype(np.float32)
    right = ((rng.random((6000, 3)) - 0.5) * np.array([0.5, 0.6, 0.6]) + np.array([0.25, 0.3, -4.0])).astype(np.float32)
    far_pipe = (rng.random((600, 3)) * np.array([3.0, 0.1, 0.1]) + np.array([2.0, 1.0, -4.0])).astype(np.float32)
    fragments = [SceneObject(name, "X", tuple(p.mean(axis=0)), (0.5, 0.6, 0.6), len(p), (0.5, 0.5, 0.5), points=p) for name, p in (("l", left), ("r", right), ("pipe", far_pipe))]
    path = write(tmp_path / "a.json", {"A": [{"label": "CRATE", "box": [0.40, 0.37, 0.60, 0.50]}]})
    scene = np.vstack([left, right, far_pipe])
    result = rebuild_objects(scene, ROOM, {"A": VP}, path, [], fragments)
    crate = result.objects[0]
    assert max(crate.size) > 0.9
    assert crate.size[1] < 0.8  # the pipe is not mostly inside, so it stays out


def test_numpy_numbers_are_written_as_plain_json(tmp_path):
    from infra.labeling.semantic_objects import read_semantic_objects, write_semantic_objects

    path = tmp_path / "o.json"
    obj = SemanticObject("S", "TANK", None, (np.float32(1.0), np.float32(2.0), np.float32(3.0)), (np.float32(1), np.float32(1), np.float32(1)), np.float32(0.1), np.int64(5), 0.5, 1)
    write_semantic_objects(path, [obj])
    assert read_semantic_objects(path)[0].point_count == 5


def test_trusted_colour_box_replaces_a_loose_hand_drawn_one_of_the_same_label(tmp_path):
    path = write(tmp_path / "a.json", {"A": [{"label": "CRATE", "box": CENTRE_BOX}]})
    tight = SemanticObject("C", "CRATE", None, (0.0, 0.15, -4.0), (0.6, 0.3, 0.6), 0.0, 100, 0.6, 1)
    result = rebuild_objects(scene_points(), ROOM, {"A": VP}, path, [], (), [tight])
    assert [o.size for o in result.objects] == [tight.size]
