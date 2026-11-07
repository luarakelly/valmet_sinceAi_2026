import math

import numpy as np

from infra.labeling.instances import OrientedBox, box_iou, cluster_instances, fit_box

rng = np.random.default_rng(0)


def solid_box(centre, size, yaw=0.0, count=2000):
    local = (rng.random((count, 3)) - 0.5) * np.array(size)
    c, s = math.cos(yaw), math.sin(yaw)
    x = local[:, 0] * c - local[:, 2] * s
    z = local[:, 0] * s + local[:, 2] * c
    return np.column_stack([x, local[:, 1], z]) + np.array(centre)


def test_two_separate_crates_become_two_instances_and_floaters_are_noise():
    a = solid_box((0, 0.5, 0), (0.6, 0.6, 0.6))
    b = solid_box((3, 0.5, 0), (0.6, 0.6, 0.6))
    floaters = rng.uniform(-5, 5, (15, 3))
    clusters = cluster_instances(np.vstack([a, b, floaters]))
    assert len(clusters) == 2
    assert sorted(len(c) for c in clusters)[0] > 1500


def test_fit_box_recovers_a_rotated_pipe():
    points = solid_box((2.0, 1.0, 1.0), (2.0, 0.2, 0.2), yaw=math.radians(30))
    box = fit_box(points)
    assert np.allclose(box.center, (2.0, 1.0, 1.0), atol=0.05)
    assert abs(max(box.size) - 2.0) < 0.1
    assert abs(min(box.size) - 0.2) < 0.06
    assert box_iou(box, OrientedBox((2.0, 1.0, 1.0), (2.0, 0.2, 0.2), math.radians(30))) > 0.7


def test_iou_identical_disjoint_and_half_overlap():
    base = OrientedBox((0, 0.5, 0), (1, 1, 1), 0.0)
    assert box_iou(base, base) == 1.0 or abs(box_iou(base, base) - 1.0) < 1e-9
    assert box_iou(base, OrientedBox((5, 0.5, 0), (1, 1, 1), 0.0)) == 0.0
    shifted = OrientedBox((0.5, 0.5, 0), (1, 1, 1), 0.0)
    assert abs(box_iou(base, shifted) - (0.5 / 1.5)) < 1e-9


def test_too_few_points_give_no_instances():
    assert cluster_instances(rng.random((10, 3))) == []
