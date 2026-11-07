"""Mask pixels → scene points: project Gaussian centres with the view's own matrix, keep the visible surface."""

from typing import List, Sequence, Tuple

import numpy as np
from scipy import ndimage

MATRIX_SIDE = 4
NEAR_PLANE = 1e-3
VISIBLE_DEPTH_TOLERANCE_M = 0.15
HOLE_FILL_PIXELS = 5  # splat centres are sparse; a hole must not let a wall behind show through
NO_DEPTH = np.inf


def project(xyz: np.ndarray, view_projection: Sequence[float]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (across, down, depth) per point; across/down are image fractions (origin top-left).

    Points behind the camera or outside the frustum depth range get depth = inf.
    """
    matrix = np.asarray(view_projection, dtype=np.float64).reshape(MATRIX_SIDE, MATRIX_SIDE).T
    clip = np.column_stack([xyz, np.ones(len(xyz))]) @ matrix.T
    depth = clip[:, 3].copy()
    is_in_front = depth > NEAR_PLANE
    safe = np.where(is_in_front, depth, 1.0)
    ndc = clip[:, :3] / safe[:, None]
    is_in_range = is_in_front & (np.abs(ndc[:, 2]) <= 1.0)
    depth[~is_in_range] = NO_DEPTH
    return ndc[:, 0] * 0.5 + 0.5, 0.5 - ndc[:, 1] * 0.5, depth


def visible_points(xyz: np.ndarray, view_projection: Sequence[float], width: int, height: int) -> np.ndarray:
    """Boolean per point: inside the image and within ±VISIBLE_DEPTH_TOLERANCE_M of the nearest surface."""
    across, down, depth = project(xyz, view_projection)
    column, row = _pixel(across, width), _pixel(down, height)
    is_inside = np.isfinite(depth) & (across >= 0) & (across < 1) & (down >= 0) & (down < 1)
    zbuffer = np.full((height, width), NO_DEPTH)
    np.minimum.at(zbuffer, (row[is_inside], column[is_inside]), depth[is_inside])
    zbuffer = ndimage.minimum_filter(zbuffer, size=HOLE_FILL_PIXELS)
    nearest = np.full(len(xyz), NO_DEPTH)
    nearest[is_inside] = zbuffer[row[is_inside], column[is_inside]]
    return is_inside & (depth <= nearest + VISIBLE_DEPTH_TOLERANCE_M)


def points_in_mask(xyz: np.ndarray, view_projection: Sequence[float], mask: np.ndarray) -> np.ndarray:
    """Indices of visible points whose pixel lies inside `mask` (H×W bool)."""
    return points_in_masks(xyz, view_projection, [mask])[0]


def points_in_masks(xyz: np.ndarray, view_projection: Sequence[float], masks: Sequence[np.ndarray]) -> List[np.ndarray]:
    """One index array per mask; projection and z-buffer are computed once for the whole view."""
    if len(masks) == 0:
        return []
    height, width = masks[0].shape
    across, down, _ = project(xyz, view_projection)
    candidates = np.flatnonzero(visible_points(xyz, view_projection, width, height))
    row, column = _pixel(down[candidates], height), _pixel(across[candidates], width)
    return [candidates[mask[row, column]] for mask in masks]


def _pixel(fraction: np.ndarray, size: int) -> np.ndarray:
    return np.clip((fraction * size).astype(int), 0, size - 1)
