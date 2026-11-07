"""Saturated-colour items (red and blue pressure tanks) found straight from the scan's colours.

Tanks are the one equipment class with a colour no wall, pipe or floor shares, so colour + a size check finds
them whole even where the 2D views were too cluttered to box them.
"""

import numpy as np
from sklearn.cluster import DBSCAN
from typing import List

from infra.labeling.semantic_objects import ID_PREFIX, SemanticObject
from infra.labeling.instances import fit_box

MIN_SATURATION = 0.55
BLUE_MIN_SATURATION = 0.45
MIN_BRIGHTNESS = 0.3
DOMINANCE = 0.45  # the two weaker channels must stay below this share of the strongest
VOXEL_M = 0.04
CLUSTER_EPS_M = 0.06
CLUSTER_MIN_VOXELS = 4
MIN_CLUSTER_VOXELS = 40
TANK_MIN_HEIGHT_M = 0.9
TANK_MAX_FOOTPRINT_M = 1.0
TANK_SCORE = 0.6
TANK_LABEL = "TANK"


def find_colour_tanks(xyz: np.ndarray, rgb: np.ndarray) -> List[SemanticObject]:
    """Tall red or blue blobs of tank size, one box per blob."""
    strongest = rgb.max(axis=1)
    saturation = (strongest - rgb.min(axis=1)) / np.maximum(strongest, 1e-6)
    red = (rgb[:, 0] == strongest) & (saturation > MIN_SATURATION) & (rgb[:, 1] < DOMINANCE * rgb[:, 0]) & (rgb[:, 2] < DOMINANCE * rgb[:, 0])
    blue = (rgb[:, 2] == strongest) & (saturation > BLUE_MIN_SATURATION) & (rgb[:, 0] < 0.6 * rgb[:, 2])
    found: List[SemanticObject] = []
    for mask in (red & (strongest > MIN_BRIGHTNESS), blue & (strongest > MIN_BRIGHTNESS)):
        found.extend(_tanks_in(xyz[mask]))
    return [_numbered(obj, number) for number, obj in enumerate(found, start=1)]


def _tanks_in(points: np.ndarray) -> List[SemanticObject]:
    if len(points) == 0:
        return []
    voxels, inverse = np.unique(np.floor(points / VOXEL_M).astype(np.int64), axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    groups = DBSCAN(eps=CLUSTER_EPS_M, min_samples=CLUSTER_MIN_VOXELS).fit_predict((voxels + 0.5) * VOXEL_M)
    tanks = []
    for group in sorted(set(groups) - {-1}):
        if (groups == group).sum() < MIN_CLUSTER_VOXELS:
            continue
        box = fit_box(points[groups[inverse] == group])
        footprint = max(box.size[0], box.size[2])
        if box.size[1] >= TANK_MIN_HEIGHT_M and footprint <= TANK_MAX_FOOTPRINT_M:
            tanks.append(SemanticObject("", TANK_LABEL, None, box.center, box.size, box.yaw, int((groups[inverse] == group).sum()), TANK_SCORE, 1))
    return tanks


def _numbered(obj: SemanticObject, number: int) -> SemanticObject:
    return SemanticObject("{}{}-C{:02d}".format(ID_PREFIX, TANK_LABEL, number), obj.label, obj.asset_class, obj.center, obj.size, obj.yaw, obj.point_count, obj.score, obj.view_count)
