"""Operator-confirmed asset placements: 2D box + camera → 3D box, and placements → scene objects.

The workbook has no real positions, so an operator boxes each asset in a rendered view. The 3D box
is fitted to the scan points that fall inside that 2D box, on the nearest surface the camera sees.
"""

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

from infra.spatial.point_cloud import PointCloud
from infra.spatial.segmentation import SceneObject

logger = logging.getLogger("ask_your_factory.placements")

PLACED_LABEL = "PLACED_ASSET"
PLACED_ID_PREFIX = "PLACED-"
CONFIRMED_STATUS = "confirmed"

MATRIX_SIDE = 4
NEAR_PLANE = 1e-3
DEPTH_GAP_M = 0.12  # a bigger jump in depth starts a new surface (equipment in front of a wall)
MIN_SURFACE_POINTS = 30
TRIM_PERCENTILES = (2.0, 98.0)  # drops floaters so they cannot stretch the box
COVERED_FRACTION = 0.5  # an extracted object this far inside a placed box is the same thing
NEUTRAL_COLOR = (0.5, 0.5, 0.5)
ROUND_DIGITS = 3


@dataclass(frozen=True)
class LiftedBox:
    center: Tuple[float, float, float]
    size: Tuple[float, float, float]
    point_count: int


def lift_box(
    xyz: np.ndarray, view_projection: Sequence[float], image_box: Sequence[float], min_share: float = 0.0
) -> Optional[LiftedBox]:
    """Fit a 3D box to the nearest surface inside `image_box`; None when nothing solid is there.

    view_projection: 16 floats, column-major (three.js Matrix4.elements).
    image_box: x0, y0, x1, y1 as fractions of the image, origin top-left.
    min_share: skip surfaces with fewer points than this share of the largest one (floaters in front).
    """
    depths, points = _points_in_view_box(xyz, view_projection, image_box)
    surface = _nearest_surface(depths, min_share)
    if len(surface) < MIN_SURFACE_POINTS:
        return None
    return _fit_box(points[surface])


def points_in_view_box(xyz: np.ndarray, view_projection: Sequence[float], image_box: Sequence[float]):
    """(depths, points) of every scan point that projects inside the 2D box."""
    return _points_in_view_box(xyz, view_projection, image_box)


def nearest_surface_indices(depths: np.ndarray, min_share: float = 0.0) -> np.ndarray:
    return _nearest_surface(depths, min_share)


def _points_in_view_box(xyz: np.ndarray, view_projection: Sequence[float], image_box: Sequence[float]):
    matrix = np.asarray(view_projection, dtype=np.float64).reshape(MATRIX_SIDE, MATRIX_SIDE).T
    clip = np.column_stack([xyz, np.ones(len(xyz))]) @ matrix.T
    is_in_front = clip[:, 3] > NEAR_PLANE
    clip = clip[is_in_front]
    points = xyz[is_in_front]
    ndc = clip[:, :3] / clip[:, 3:4]
    across = ndc[:, 0] * 0.5 + 0.5
    down = 0.5 - ndc[:, 1] * 0.5
    x0, y0, x1, y1 = image_box
    is_in_box = (across >= x0) & (across <= x1) & (down >= y0) & (down <= y1) & (np.abs(ndc[:, 2]) <= 1.0)
    return clip[is_in_box, 3], points[is_in_box]


def _nearest_surface(depths: np.ndarray, min_share: float = 0.0) -> np.ndarray:
    """Indices of the closest depth cluster that is dense enough to be a real surface."""
    order = np.argsort(depths)
    jumps = np.flatnonzero(np.diff(depths[order]) > DEPTH_GAP_M) + 1
    surfaces = np.split(order, jumps)
    needed = max(MIN_SURFACE_POINTS, min_share * max((len(s) for s in surfaces), default=0))
    for surface in surfaces:
        if len(surface) >= needed:
            return surface
    return order[:0]


def _fit_box(points: np.ndarray) -> LiftedBox:
    low, high = np.percentile(points, TRIM_PERCENTILES, axis=0)
    kept = points[((points >= low) & (points <= high)).all(axis=1)]
    lo, hi = kept.min(axis=0), kept.max(axis=0)
    return LiftedBox(
        center=_rounded((lo + hi) / 2.0),
        size=_rounded(hi - lo),
        point_count=len(kept),
    )


def placed_objects(cloud: PointCloud, placements: Dict[str, Dict[str, Any]], asset_ids: Set[str]) -> Dict[str, SceneObject]:
    """asset_id → scene object for every stored placement that still names a known asset."""
    placed: Dict[str, SceneObject] = {}
    for asset_id, record in placements.items():
        box = _stored_box(record)
        if asset_id not in asset_ids or box is None:
            logger.warning("Ignoring placement for %s: unknown asset or malformed box", asset_id)
            continue
        placed[asset_id] = _scene_object(cloud, asset_id, *box)
    return placed


def drop_covered(objects: List[SceneObject], placed: Sequence[SceneObject]) -> List[SceneObject]:
    """Extracted objects that sit mostly inside a placed box: the placement replaces them."""
    return [obj for obj in objects if not any(_is_covered(obj, box) for box in placed)]


def _stored_box(record: Dict[str, Any]) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    try:
        center = np.asarray(record["center"], dtype=np.float64)
        size = np.asarray(record["size"], dtype=np.float64)
    except (KeyError, TypeError, ValueError):
        return None
    is_well_formed = center.shape == (3,) and size.shape == (3,) and bool((size > 0).all())
    if not is_well_formed:
        return None
    return center, size


def _scene_object(cloud: PointCloud, asset_id: str, center: np.ndarray, size: np.ndarray) -> SceneObject:
    inside = (np.abs(cloud.xyz - center) <= size / 2.0).all(axis=1)
    color = NEUTRAL_COLOR
    if inside.any():
        color = tuple(round(float(v), ROUND_DIGITS) for v in cloud.rgb[inside].mean(axis=0))
    return SceneObject(
        object_id=PLACED_ID_PREFIX + asset_id,
        label=PLACED_LABEL,
        center=_rounded(center),
        size=_rounded(size),
        point_count=int(inside.sum()),
        color=color,
        points=cloud.xyz[inside].astype(np.float32),
    )


def _is_covered(obj: SceneObject, box: SceneObject) -> bool:
    overlap_low = np.maximum(_corner(obj, -1), _corner(box, -1))
    overlap_high = np.minimum(_corner(obj, 1), _corner(box, 1))
    overlap_volume = np.prod(np.clip(overlap_high - overlap_low, 0.0, None))
    return overlap_volume >= COVERED_FRACTION * np.prod(obj.size)


def _corner(obj: SceneObject, side: int) -> np.ndarray:
    return np.asarray(obj.center) + side * np.asarray(obj.size) / 2.0


def _rounded(values: np.ndarray) -> Tuple[float, float, float]:
    return tuple(round(float(v), ROUND_DIGITS) for v in values)
