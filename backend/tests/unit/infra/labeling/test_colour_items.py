import numpy as np

from infra.labeling.colour_items import find_colour_tanks

rng = np.random.default_rng(2)


def blob(centre, size, colour, count=6000):
    points = (rng.random((count, 3)) - 0.5) * np.array(size) + np.array(centre)
    return points, np.tile(np.array(colour, dtype=float), (count, 1))


def test_red_and_blue_tanks_are_found_and_small_or_wall_coloured_things_are_not():
    red_xyz, red_rgb = blob((0, 0.7, 0), (0.6, 1.4, 0.6), (0.8, 0.1, 0.1))
    blue_xyz, blue_rgb = blob((3, 0.7, 0), (0.6, 1.2, 0.6), (0.1, 0.2, 0.8))
    pump_xyz, pump_rgb = blob((6, 1.0, 0), (0.3, 0.3, 0.3), (0.8, 0.1, 0.1), count=3000)
    wall_xyz, wall_rgb = blob((9, 1.0, 0), (0.3, 1.5, 6.0), (0.6, 0.6, 0.55), count=8000)
    tanks = find_colour_tanks(np.vstack([red_xyz, blue_xyz, pump_xyz, wall_xyz]), np.vstack([red_rgb, blue_rgb, pump_rgb, wall_rgb]))
    assert sorted(round(t.center[0]) for t in tanks) == [0, 3]
    assert all(t.label == "TANK" and t.size[1] > 1.0 for t in tanks)


def test_no_coloured_points_gives_no_tanks():
    assert find_colour_tanks(np.zeros((5, 3)), np.full((5, 3), 0.5)) == []
