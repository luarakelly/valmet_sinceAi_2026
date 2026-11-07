import numpy as np

from infra.labeling.backprojection import points_in_mask, visible_points
from infra.labeling.fusion import NO_LABEL, LabelVotes, add_view_masks
from tests.unit.infra.spatial.test_placements import camera_at_origin_looking_down_minus_z

SIZE = 64
LABEL_PIPE, LABEL_VALVE = 0, 1


def wall_with_pipe():
    """Wall at z=-8 (dense grid) and a thin pipe at z=-3 covering the image centre."""
    gx, gy = np.meshgrid(np.linspace(-6, 6, 120), np.linspace(-6, 6, 120))
    wall = np.column_stack([gx.ravel(), gy.ravel(), np.full(gx.size, -8.0)])
    px, py = np.meshgrid(np.linspace(-0.4, 0.4, 20), np.linspace(-1.0, 1.0, 40))
    pipe = np.column_stack([px.ravel(), py.ravel(), np.full(px.size, -3.0)])
    return np.vstack([wall, pipe]), len(wall)


def centre_mask():
    """Pixels fully covered by the pipe (it spans about columns 28-36, rows 23-41)."""
    mask = np.zeros((SIZE, SIZE), dtype=bool)
    mask[26:38, 29:35] = True
    return mask


def test_thin_pipe_in_front_of_wall_selects_the_pipe_not_the_wall():
    xyz, wall_count = wall_with_pipe()
    vp = camera_at_origin_looking_down_minus_z()
    chosen = points_in_mask(xyz, vp, centre_mask())
    assert len(chosen) > 0
    assert (chosen >= wall_count).all()


def test_points_behind_camera_are_not_visible():
    vp = camera_at_origin_looking_down_minus_z()
    assert not visible_points(np.array([[0.0, 0.0, 4.0]]), vp, SIZE, SIZE).any()


def test_label_needs_votes_from_two_views():
    votes = LabelVotes.empty(3, 2)
    add_view_masks(votes, [(np.array([0, 1]), LABEL_PIPE, 0.9)])
    add_view_masks(votes, [(np.array([0]), LABEL_PIPE, 0.8)])
    assigned = votes.assign()
    assert assigned[0] == LABEL_PIPE
    assert assigned[1] == NO_LABEL  # one-off detection
    assert assigned[2] == NO_LABEL


def test_majority_label_by_score_wins():
    votes = LabelVotes.empty(1, 2)
    for score in (0.9, 0.8):
        add_view_masks(votes, [(np.array([0]), LABEL_VALVE, score)])
    add_view_masks(votes, [(np.array([0]), LABEL_PIPE, 0.4)])
    add_view_masks(votes, [(np.array([0]), LABEL_PIPE, 0.4)])
    assert votes.assign()[0] == LABEL_VALVE


def test_two_masks_in_one_view_count_as_one_view():
    votes = LabelVotes.empty(1, 1)
    add_view_masks(votes, [(np.array([0]), LABEL_PIPE, 0.9), (np.array([0]), LABEL_PIPE, 0.7)])
    assert votes.assign()[0] == NO_LABEL
