import numpy as np

from infra.labeling.backprojection import project
from infra.labeling.pack_coverage import coverage_report
from infra.labeling.pipeline import ViewDetections, build_semantic_objects
from infra.labeling.segmenter import Detection
from infra.labeling.semantic_objects import SemanticObject
from infra.labeling.vocabulary import term_for_phrase
from tests.unit.infra.spatial.test_placements import camera_at_origin_looking_down_minus_z

SIZE = 64


def cube(centre, side=0.8, count=12000, seed=0):
    rng = np.random.default_rng(seed)
    return (rng.random((count, 3)) - 0.5) * side + np.array(centre)


def mask_around(points, vp, pad=2):
    across, down, depth = project(points, vp)
    mask = np.zeros((SIZE, SIZE), dtype=bool)
    mask[max(0, int(down.min() * SIZE) - pad): int(down.max() * SIZE) + pad, max(0, int(across.min() * SIZE) - pad): int(across.max() * SIZE) + pad] = True
    return mask


def test_a_crate_seen_in_two_views_becomes_one_labelled_box():
    crate = cube((0.0, 0.0, -4.0))
    floaters = np.array([[3.0, 0.0, -6.0]])
    xyz = np.vstack([crate, floaters])
    vp = camera_at_origin_looking_down_minus_z()
    detection = Detection(term_for_phrase("crate"), 0.9, mask_around(crate, vp))
    views = [ViewDetections(vp, [detection]), ViewDetections(vp, [detection])]
    objects = build_semantic_objects(xyz, views)
    assert [o.label for o in objects] == ["CRATE"]
    assert abs(objects[0].center[2] + 4.0) < 0.5  # one direction sees only the front slab
    assert objects[0].view_count == 2


def test_single_view_detection_creates_nothing():
    crate = cube((0.0, 0.0, -4.0))
    vp = camera_at_origin_looking_down_minus_z()
    detection = Detection(term_for_phrase("crate"), 0.9, mask_around(crate, vp))
    assert build_semantic_objects(crate, [ViewDetections(vp, [detection])]) == []


def test_no_views_gives_no_objects():
    assert build_semantic_objects(cube((0, 0, -4)), []) == []


def asset(asset_class):
    return {"asset_class": asset_class}


def semantic(label, asset_class):
    return SemanticObject("x", label, asset_class, (0, 0, 0), (1, 1, 1), 0.0, 100, 0.8, 3)


def test_coverage_reports_found_missing_and_extras():
    assets = [asset("PROCESS_PUMP")] * 6 + [asset("CONTROL_VALVE")] * 12
    objects = [semantic("PUMP", "PROCESS_PUMP")] * 2 + [semantic("CRATE", None), semantic("PIPE", None), semantic("PIPE", None)]
    report = coverage_report(assets, objects)
    assert report["classes"]["PROCESS_PUMP"] == {"in_workbook": 6, "found_in_scan": 2, "missing": 4}
    assert report["classes"]["CONTROL_VALVE"]["missing"] == 12
    assert report["other_objects"] == {"CRATE": 1, "PIPE": 2}
