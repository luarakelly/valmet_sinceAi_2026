"""Photoreal viewer export: raw 3D Gaussian Splat → compact `.splat` in the canonical scene frame.

The raw scan (`Equipment Room.ply`, 395 MB, 59 floats per splat) is too heavy for a
browser. This writes the widely supported 32-byte `.splat` layout (antimatter15):

    position float32×3 · scale float32×3 (linear) · RGBA uint8×4 · rotation uint8×4 (w, x, y, z)

Positions and rotations are moved into the same frame as every other scene output (Y up, floor at
y = 0, room centred), using the exact transform fitted by `point_cloud.canonical_transform`, so the
splat lines up with the extracted frames, the robot route and the labels. View-dependent colour
(higher SH bands) is dropped; only the base colour is kept.
"""

import logging
from pathlib import Path
from typing import Dict

import numpy as np

from infra.spatial.point_cloud import (
    DATA_DIR,
    RAW_SPLAT_PATH,
    SH_C0,
    _confident_splats,
    _read_ply,
    canonical_transform,
    valid_splat_rows,
)

logger = logging.getLogger("ask_your_factory.splat_export")

VIEWER_SPLAT_PATH = DATA_DIR / "Equipment_Room.splat"

# Rendering keeps faint splats (they make surfaces look continuous) but drops near-invisible ones
# and the huge "floater" splats typical of capture noise.
MIN_RENDER_OPACITY = 0.03
MAX_RENDER_SCALE = 0.5

SPLAT_DTYPE = np.dtype([
    ("position", "<f4", (3,)),
    ("scale", "<f4", (3,)),
    ("rgba", "u1", (4,)),
    ("rotation", "u1", (4,)),
])


def build_viewer_splat(raw_path: Path = RAW_SPLAT_PATH, out_path: Path = VIEWER_SPLAT_PATH) -> Path:
    """Convert the raw splat to the viewer `.splat` and return its path."""
    columns = _read_ply(raw_path)
    confident_xyz, _ = _confident_splats(columns)  # same fit as the point cloud → same frame
    to_canonical = canonical_transform(confident_xyz)
    records = splat_records(columns, to_canonical)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".splat.tmp")
    records.tofile(tmp)
    tmp.replace(out_path)
    logger.info("Wrote %d splats (%.1f MB) to %s", len(records), out_path.stat().st_size / 1e6, out_path.name)
    return out_path


def ensure_viewer_splat() -> Path:
    """The viewer splat, built once from the raw scan if it is missing."""
    if VIEWER_SPLAT_PATH.exists():
        return VIEWER_SPLAT_PATH
    if not RAW_SPLAT_PATH.exists():
        raise FileNotFoundError("Photoreal scene needs data/input/'Equipment Room.ply' (or a prebuilt .splat)")
    return build_viewer_splat()


def splat_records(columns: Dict[str, np.ndarray], to_canonical) -> np.ndarray:
    """Filtered, canonical-frame splat records sorted by visual weight (largest, most opaque first)."""
    columns = {name: values[valid_splat_rows(columns)] for name, values in columns.items()}
    with np.errstate(over="ignore", invalid="ignore"):
        raw_xyz = np.column_stack([columns["x"], columns["y"], columns["z"]]).astype(np.float64)
        log_scale = np.column_stack([columns[f"scale_{i}"] for i in range(3)]).astype(np.float64)
        scale = np.exp(np.clip(log_scale, -20, 5))
        opacity = 1.0 / (1.0 + np.exp(-np.clip(columns["opacity"].astype(np.float64), -50, 50)))
        rgb = np.clip(0.5 + SH_C0 * np.column_stack([columns[f"f_dc_{i}"] for i in range(3)]), 0.0, 1.0)
        quat = np.column_stack([columns["rot_0"], columns["rot_1"], columns["rot_2"], columns["rot_3"]]).astype(np.float64)

    xyz, inside = to_canonical(raw_xyz)
    norm = np.linalg.norm(quat, axis=1)
    keep = (
        inside
        & (opacity > MIN_RENDER_OPACITY)
        & (scale.max(axis=1) < MAX_RENDER_SCALE)
        & np.isfinite(xyz).all(axis=1)
        & np.isfinite(rgb).all(axis=1)
        & (norm > 1e-8)
    )
    xyz, scale, opacity, rgb = xyz[keep], scale[keep], opacity[keep], rgb[keep]
    quat = rotate_180_about_x(quat[keep] / norm[keep, None])

    order = np.argsort(-(scale.prod(axis=1) * opacity))
    records = np.empty(len(order), dtype=SPLAT_DTYPE)
    records["position"] = xyz[order]
    records["scale"] = scale[order]
    records["rgba"][:, :3] = np.round(rgb[order] * 255.0)
    records["rgba"][:, 3] = np.round(opacity[order] * 255.0)
    records["rotation"] = np.clip(np.round(quat[order] * 128.0 + 128.0), 0, 255)
    return records


def rotate_180_about_x(quat_wxyz: np.ndarray) -> np.ndarray:
    """Left-multiply by the 180° X rotation (0, 1, 0, 0) used for positions (COLMAP Y-down → Y-up)."""
    w, x, y, z = quat_wxyz.T
    return np.column_stack([-x, w, -z, y])
