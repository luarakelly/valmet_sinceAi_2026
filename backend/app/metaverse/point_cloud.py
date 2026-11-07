"""Point-cloud loading for the boiler room scan.

Everything downstream works in one canonical frame: metres-like scan units, Y up, floor at y = 0,
room centred on x = z = 0.
The raw 3D Gaussian Splat uses the COLMAP convention (Y down), so it is rotated 180° about X.

Sources, in order of preference:
1. Raw splat `Industrial Boiler Room.ply` (gitignored, 355 MB): filtered, canonicalised, and
   exported as the viewer PLY.
2. Viewer PLY `Industrial_Boiler_Room_standard.ply` (tracked, already canonical).
"""

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import numpy as np

from app.metaverse.dataset import DATA_DIR

logger = logging.getLogger("ask_your_factory.point_cloud")

RAW_SPLAT_NAME = "Industrial Boiler Room.ply"
# The raw scan is gitignored; it may live in data/ or data/input/.
RAW_SPLAT_PATH = next(
    (p for p in (DATA_DIR / RAW_SPLAT_NAME, DATA_DIR / "input" / RAW_SPLAT_NAME) if p.exists()),
    DATA_DIR / RAW_SPLAT_NAME,
)
VIEWER_PLY_PATH = DATA_DIR / "Industrial_Boiler_Room_standard.ply"
VIEWER_MESH_PATH = DATA_DIR / "Industrial_Boiler_Room_mesh.ply"

# Marks a viewer PLY written by this module, so stale exports in other frames are regenerated.
CANONICAL_MARKER = "comment frame y-up floor-zero v2 clean-records"

SH_C0 = 0.28209479177387814  # Zeroth spherical-harmonic band → RGB
MIN_OPACITY = 0.15
MAX_SPLAT_SCALE = 0.3
CROP_PERCENTILES = (2.0, 98.0)
CROP_MARGIN = 0.3
FLOOR_BIN = 0.02

PLY_TYPES = {"float": "<f4", "float32": "<f4", "double": "<f8", "uchar": "u1", "uint8": "u1", "int": "<i4"}


@dataclass(frozen=True)
class PointCloud:
    """Canonical scene points (N×3, Y up, floor at 0) with RGB colours in [0, 1]."""

    xyz: np.ndarray
    rgb: np.ndarray
    source: Path

    def __len__(self) -> int:
        return len(self.xyz)


def load_scene_cloud() -> PointCloud:
    """Load the canonical scene cloud, regenerating the viewer PLY from the raw splat when needed."""
    if RAW_SPLAT_PATH.exists():
        if not _is_canonical_export(VIEWER_PLY_PATH):
            cloud = _canonicalise_splat(RAW_SPLAT_PATH)
            write_viewer_ply(cloud, VIEWER_PLY_PATH)
            logger.info("Exported %d canonical points to %s", len(cloud), VIEWER_PLY_PATH.name)
            return cloud
    elif not VIEWER_PLY_PATH.exists():
        raise FileNotFoundError(f"No scene point cloud found in {DATA_DIR}")
    elif not _is_canonical_export(VIEWER_PLY_PATH):
        raise ValueError(f"{VIEWER_PLY_PATH.name} predates the canonical frame; add the raw splat to regenerate it")

    columns = _read_ply(VIEWER_PLY_PATH)
    xyz = np.column_stack([columns["x"], columns["y"], columns["z"]]).astype(np.float32)
    rgb = np.column_stack([columns["red"], columns["green"], columns["blue"]]).astype(np.float32) / 255.0
    return PointCloud(xyz=xyz, rgb=rgb, source=VIEWER_PLY_PATH)


def write_viewer_ply(cloud: PointCloud, path: Path) -> None:
    """Write a compact binary PLY (xyz float32 + rgb uint8) for the Three.js PLYLoader."""
    packed = np.empty(len(cloud), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("red", "u1"), ("green", "u1"), ("blue", "u1")])
    for axis, name in enumerate(("x", "y", "z")):
        packed[name] = cloud.xyz[:, axis]
    rgb8 = np.clip(cloud.rgb * 255.0, 0, 255).astype(np.uint8)
    for channel, name in enumerate(("red", "green", "blue")):
        packed[name] = rgb8[:, channel]

    header = "\n".join([
        "ply",
        "format binary_little_endian 1.0",
        CANONICAL_MARKER,
        f"element vertex {len(cloud)}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        "end_header",
        "",
    ])
    with open(path, "wb") as handle:
        handle.write(header.encode("ascii"))
        packed.tofile(handle)


def _canonicalise_splat(path: Path) -> PointCloud:
    """Filter splat noise, rotate to Y-up and shift the floor to y = 0."""
    columns = _read_ply(path)
    xyz, rgb = _confident_splats(columns)
    to_canonical = canonical_transform(xyz)
    xyz, inside = to_canonical(xyz)
    return PointCloud(xyz=xyz[inside].astype(np.float32), rgb=rgb[inside].astype(np.float32), source=path)


def valid_splat_rows(columns: Dict[str, np.ndarray]) -> np.ndarray:
    """Mask of records whose every field is a plausible splat value.

    The supplied scan is corrupted after ~502k of its 1.5M records (random bytes). About half of
    that noise passes per-field filters and lands as junk near the origin; requiring every one of
    the 59 fields to be finite and |v| < 1e3 rejects all of it while keeping all real splats.
    """
    valid = np.ones(len(columns["x"]), dtype=bool)
    with np.errstate(invalid="ignore"):
        for values in columns.values():
            valid &= np.abs(values.astype(np.float64)) < 1e3  # NaN compares False
    position_mag = np.abs(np.column_stack([columns["x"], columns["y"], columns["z"]]).astype(np.float64)).max(axis=1)
    return valid & (position_mag > 1e-8)


def _confident_splats(columns: Dict[str, np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    columns = {name: values[valid_splat_rows(columns)] for name, values in columns.items()}
    with np.errstate(over="ignore", invalid="ignore"):
        xyz = np.column_stack([columns["x"], columns["y"], columns["z"]]).astype(np.float64)
        opacity = 1.0 / (1.0 + np.exp(-np.clip(columns["opacity"], -50, 50)))
        scale = np.exp(np.clip(np.column_stack([columns[f"scale_{i}"] for i in range(3)]), -20, 5)).max(axis=1)
        rgb = np.clip(0.5 + SH_C0 * np.column_stack([columns[f"f_dc_{i}"] for i in range(3)]), 0.0, 1.0)
    keep = np.isfinite(xyz).all(axis=1) & np.isfinite(rgb).all(axis=1) & (opacity > MIN_OPACITY) & (scale < MAX_SPLAT_SCALE)
    return xyz[keep], rgb[keep]


def canonical_transform(raw_xyz: np.ndarray) -> Callable[[np.ndarray], Tuple[np.ndarray, np.ndarray]]:
    """Fit the raw-splat → canonical frame transform on confident splat centres.

    Returns `f(raw_xyz) -> (canonical_xyz, inside_mask)`: 180° about X (COLMAP Y-down → Y-up,
    keeps handedness), percentile crop, floor to y = 0, room centred on x = z = 0.
    """
    flipped = raw_xyz * np.array([1.0, -1.0, -1.0])
    low, high = np.percentile(flipped, CROP_PERCENTILES, axis=0)
    inside = ((flipped > low - CROP_MARGIN) & (flipped < high + CROP_MARGIN)).all(axis=1)
    floor = _floor_height(flipped[inside, 1])
    centre = (low + high) / 2.0
    shift = np.array([centre[0], floor, centre[2]])

    def apply(xyz: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        f = xyz * np.array([1.0, -1.0, -1.0])
        mask = ((f > low - CROP_MARGIN) & (f < high + CROP_MARGIN)).all(axis=1)
        return f - shift, mask

    return apply


def build_scene_mesh(force: bool = False) -> Path:
    """Write the viewer mesh (surface reconstructed from the raw splat) if missing or stale."""
    from app.metaverse import splat_mesh

    if not force and splat_mesh.is_mesh_export(VIEWER_MESH_PATH):
        return VIEWER_MESH_PATH
    if not RAW_SPLAT_PATH.exists():
        raise FileNotFoundError(f"{RAW_SPLAT_PATH.name} is needed to build the scene mesh")
    columns = _read_ply(RAW_SPLAT_PATH)
    xyz, _ = _confident_splats(columns)
    valid = valid_splat_rows(columns)
    columns = {name: values[valid] for name, values in columns.items()}
    splat_mesh.build_mesh(columns, canonical_transform(xyz), VIEWER_MESH_PATH)
    return VIEWER_MESH_PATH


def _floor_height(heights: np.ndarray) -> float:
    """Densest horizontal layer in the lower half of the scan: the floor."""
    bins = np.arange(heights.min(), heights.max() + FLOOR_BIN, FLOOR_BIN)
    counts, edges = np.histogram(heights, bins=bins)
    lower_half = counts[: len(counts) // 2]
    densest = int(np.argmax(lower_half))
    return float(edges[densest] + FLOOR_BIN / 2)


def _is_canonical_export(path: Path) -> bool:
    if not path.exists():
        return False
    header, _ = _read_header(path)
    return CANONICAL_MARKER in header


def _read_header(path: Path) -> Tuple[List[str], int]:
    lines: List[str] = []
    with open(path, "rb") as handle:
        while True:
            line = handle.readline()
            if not line:
                raise ValueError(f"{path.name}: missing end_header")
            lines.append(line.decode("ascii", errors="replace").strip())
            if lines[-1] == "end_header":
                return lines, handle.tell()


def _read_ply(path: Path) -> Dict[str, np.ndarray]:
    """Read the vertex element of a binary little-endian PLY into named columns (one sequential read)."""
    header, offset = _read_header(path)
    if "format binary_little_endian 1.0" not in header:
        raise ValueError(f"{path.name}: only binary little-endian PLY is supported")

    count = 0
    fields: List[Tuple[str, str]] = []
    in_vertex = False
    for line in header:
        parts = line.split()
        if parts[:2] == ["element", "vertex"]:
            count = int(parts[2])
            in_vertex = True
        elif parts and parts[0] == "element":
            in_vertex = False
        elif in_vertex and parts and parts[0] == "property":
            fields.append((parts[2], PLY_TYPES[parts[1]]))

    vertices = np.fromfile(path, dtype=np.dtype(fields), count=count, offset=offset)
    return {name: vertices[name] for name, _ in fields}
