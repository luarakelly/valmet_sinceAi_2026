"""Labelled points → instances (DBSCAN per label) → gravity-aligned oriented boxes."""

from dataclasses import dataclass
import math
from typing import List, Tuple

import numpy as np
from sklearn.cluster import DBSCAN

DBSCAN_EPS_M = 0.10
DBSCAN_MIN_SAMPLES = 30
TRIM_PERCENTILES = (1.0, 99.0)  # floaters must not stretch a box
MIN_EXTENT_M = 0.02
YAW_SEARCH_STEPS = 90  # 2° resolution over the half turn a rectangle is symmetric under


@dataclass(frozen=True)
class OrientedBox:
    """Upright box: centre, full size (x along yaw, y up, z across) and yaw about the vertical axis (radians)."""

    center: Tuple[float, float, float]
    size: Tuple[float, float, float]
    yaw: float


def cluster_instances(xyz: np.ndarray, eps: float = DBSCAN_EPS_M, min_samples: int = DBSCAN_MIN_SAMPLES) -> List[np.ndarray]:
    """Index arrays of each DBSCAN cluster; noise is dropped."""
    if len(xyz) < min_samples:
        return []
    cluster_of = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(xyz)
    return [np.flatnonzero(cluster_of == cluster) for cluster in sorted(set(cluster_of) - {-1})]


def fit_box(points: np.ndarray) -> OrientedBox:
    """Minimum-area rectangle in the floor plane (yaw search), tight height; trimmed against floaters."""
    low, high = np.percentile(points, TRIM_PERCENTILES, axis=0)
    kept = points[((points >= low) & (points <= high)).all(axis=1)]
    if len(kept) == 0:
        kept = points
    xz = kept[:, [0, 2]]
    yaw = _best_yaw(xz)
    rotated = xz @ _rotation(yaw)
    lo, hi = rotated.min(axis=0), rotated.max(axis=0)
    centre_xz = ((lo + hi) / 2.0) @ _rotation(yaw).T
    y_lo, y_hi = kept[:, 1].min(), kept[:, 1].max()
    size = (max(hi[0] - lo[0], MIN_EXTENT_M), max(y_hi - y_lo, MIN_EXTENT_M), max(hi[1] - lo[1], MIN_EXTENT_M))
    return OrientedBox((float(centre_xz[0]), float((y_lo + y_hi) / 2.0), float(centre_xz[1])), size, float(yaw))


def box_iou(a: OrientedBox, b: OrientedBox) -> float:
    """3D IoU of two upright boxes: convex footprint clip × vertical overlap."""
    overlap_area = _polygon_area(_clip(_footprint(a), _footprint(b)))
    overlap_height = max(0.0, min(_top(a), _top(b)) - max(_bottom(a), _bottom(b)))
    intersection = overlap_area * overlap_height
    union = _volume(a) + _volume(b) - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def _best_yaw(xz: np.ndarray) -> float:
    best_yaw, best_area = 0.0, math.inf
    for step in range(YAW_SEARCH_STEPS):
        yaw = step * math.pi / 2.0 / YAW_SEARCH_STEPS
        rotated = xz @ _rotation(yaw)
        extent = rotated.max(axis=0) - rotated.min(axis=0)
        if extent[0] * extent[1] < best_area:
            best_yaw, best_area = yaw, extent[0] * extent[1]
    return best_yaw


def _rotation(yaw: float) -> np.ndarray:
    """Columns are the box axes in the XZ plane (x along yaw)."""
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s], [s, c]])


def _footprint(box: OrientedBox) -> np.ndarray:
    half = np.array([box.size[0], box.size[2]]) / 2.0
    corners = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]]) * half
    return corners @ _rotation(box.yaw).T + np.array([box.center[0], box.center[2]])


def _top(box: OrientedBox) -> float:
    return box.center[1] + box.size[1] / 2.0


def _bottom(box: OrientedBox) -> float:
    return box.center[1] - box.size[1] / 2.0


def _volume(box: OrientedBox) -> float:
    return box.size[0] * box.size[1] * box.size[2]


def _clip(subject: np.ndarray, clipper: np.ndarray) -> np.ndarray:
    """Sutherland–Hodgman: clip convex `subject` by convex counter-clockwise `clipper`."""
    output = list(subject)
    for start, end in zip(clipper, np.roll(clipper, -1, axis=0)):
        polygon, output = output, []
        for current, following in zip(polygon, polygon[1:] + polygon[:1]):
            current_in, following_in = _is_left(start, end, current), _is_left(start, end, following)
            if current_in != following_in:
                output.append(_crossing(start, end, current, following))
            if following_in:
                output.append(following)
        if not output:
            return np.zeros((0, 2))
    return np.array(output)


def _is_left(start: np.ndarray, end: np.ndarray, point: np.ndarray) -> bool:
    return (end[0] - start[0]) * (point[1] - start[1]) - (end[1] - start[1]) * (point[0] - start[0]) >= 0


def _crossing(a1, a2, b1, b2) -> np.ndarray:
    da, db = a2 - a1, b2 - b1
    denominator = da[0] * db[1] - da[1] * db[0]
    t = ((b1[0] - a1[0]) * db[1] - (b1[1] - a1[1]) * db[0]) / denominator
    return a1 + t * da


def _polygon_area(polygon: np.ndarray) -> float:
    if len(polygon) < 3:
        return 0.0
    x, y = polygon[:, 0], polygon[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)
