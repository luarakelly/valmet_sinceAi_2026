"""Gaussian splat → coloured surface mesh for the viewer.

A 3DGS scene is a cloud of anisotropic Gaussians, not a surface; drawing their centres as points
gives a soft, mushy image. This module turns the splat into a triangle mesh:

1. Keep confident Gaussians and move them into the canonical frame (Y up, floor at 0, centred).
2. Draw samples from each Gaussian's covariance, more for larger ones, so flat wall and floor
   Gaussians fill their full footprint instead of leaving holes between centres.
3. Accumulate opacity and colour into a voxel grid, smooth it, and extract the iso-surface with
   marching cubes.
4. Drop floating fragments, decimate, and resample vertex colours from the colour grid.

The result is written as a binary PLY with faces and vertex colours (Three.js PLYLoader reads it).
"""

from dataclasses import dataclass
import logging
import time
from pathlib import Path
from typing import Callable, Dict, Tuple

import numpy as np
from scipy import ndimage

logger = logging.getLogger("ask_your_factory.splat_mesh")

MESH_MARKER = "comment splat-mesh v5"

VOXEL = 0.015                # metres per voxel
MIN_OPACITY = 0.05
MAX_SPLAT_SCALE = 0.25
SAMPLE_SIGMA_CLIP = 1.8
MAX_SAMPLES_PER_SPLAT = 24
SMOOTH_SIGMA = 1.0           # voxels
COLOUR_SIGMA = 1.5           # voxels
ISO_LEVEL = 0.013            # accumulated opacity per voxel after smoothing (tuned for 1.5 cm voxels)
MIN_COMPONENT_FACES = 400
TARGET_FACES = 700_000
CEILING_CLEARANCE = 0.12     # metres cut below the detected ceiling so the room is open from above

Transform = Callable[[np.ndarray], Tuple[np.ndarray, np.ndarray]]


@dataclass
class SplatGrid:
    density: np.ndarray      # (X, Y, Z) accumulated opacity
    colour: np.ndarray       # (X, Y, Z, 3) mean colour in [0, 1]
    origin: np.ndarray       # world position of voxel (0, 0, 0)
    ceiling: float
    voxel: float


def build_mesh(columns: Dict[str, np.ndarray], to_canonical: Transform, path: Path) -> Tuple[int, int]:
    """Build the mesh from raw splat columns and write it to `path`. Returns (vertices, faces).

    `to_canonical(xyz) -> (xyz, keep_mask)` applies the same frame transform and crop as the
    point cloud, so the mesh lines up with frames and navigation.
    """
    started = time.perf_counter()
    grid = accumulate(columns, to_canonical)
    verts, faces, rgb = extract_surface(grid)
    _write_mesh_ply(path, verts, rgb, faces)
    logger.info("Splat mesh: %d vertices / %d faces in %.1fs", len(verts), len(faces), time.perf_counter() - started)
    return len(verts), len(faces)


def accumulate(columns: Dict[str, np.ndarray], to_canonical: Transform, voxel: float = VOXEL) -> SplatGrid:
    """Sample every Gaussian into a voxel grid of opacity and colour."""
    rng = np.random.default_rng(7)
    with np.errstate(over="ignore", invalid="ignore"):
        xyz = np.column_stack([columns["x"], columns["y"], columns["z"]]).astype(np.float64)
        opacity = 1.0 / (1.0 + np.exp(-np.clip(columns["opacity"], -50, 50)))
        scales = np.exp(np.clip(np.column_stack([columns[f"scale_{i}"] for i in range(3)]), -20, 5))
        quat = np.column_stack([columns["rot_0"], columns["rot_1"], columns["rot_2"], columns["rot_3"]]).astype(np.float64)
        rgb = np.clip(0.5 + 0.28209479177387814 * np.column_stack([columns[f"f_dc_{i}"] for i in range(3)]), 0.0, 1.0)

    keep = (opacity > MIN_OPACITY) & (scales.max(axis=1) < MAX_SPLAT_SCALE) & (np.linalg.norm(quat, axis=1) > 1e-6)
    xyz, opacity, scales, quat, rgb = xyz[keep], opacity[keep], scales[keep], quat[keep], rgb[keep]
    canonical, inside = to_canonical(xyz)
    xyz, opacity, scales, quat, rgb = canonical[inside], opacity[inside], scales[inside], quat[inside], rgb[inside]

    # Rotation matrices, then the same 180° turn about X that `to_canonical` applies to positions.
    quat /= np.linalg.norm(quat, axis=1, keepdims=True)
    w, x, y, z = quat.T
    rot = np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], axis=1),
        np.stack([2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], axis=1),
        np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], axis=1),
    ], axis=1)
    rot[:, 1:, :] *= -1.0

    origin = xyz.min(axis=0) - 3 * voxel
    dims = np.ceil((xyz.max(axis=0) + 3 * voxel - origin) / voxel).astype(int) + 1
    size = int(np.prod(dims))
    density = np.zeros(size, dtype=np.float64)
    colour = np.zeros((size, 3), dtype=np.float64)

    # Samples per Gaussian ∝ its footprint in voxels, so big flat splats cover their full extent.
    s_sorted = np.sort(scales, axis=1)
    footprint = (2 * s_sorted[:, 2]) * (2 * s_sorted[:, 1]) / (voxel * voxel)
    counts = np.clip(np.ceil(footprint), 1, MAX_SAMPLES_PER_SPLAT).astype(int)

    for k in range(1, MAX_SAMPLES_PER_SPLAT + 1):
        idx = np.nonzero(counts == k)[0]
        if len(idx) == 0:
            continue
        offsets = np.clip(rng.standard_normal((len(idx), k, 3)), -SAMPLE_SIGMA_CLIP, SAMPLE_SIGMA_CLIP) * scales[idx, None, :]
        points = (xyz[idx, None, :] + np.einsum("nij,nkj->nki", rot[idx], offsets)).reshape(-1, 3)
        weights = np.repeat(opacity[idx] / k, k)
        colours = np.repeat(rgb[idx], k, axis=0)
        cells = np.floor((points - origin) / voxel).astype(int)
        valid = ((cells >= 0) & (cells < dims)).all(axis=1)
        flat = np.ravel_multi_index(cells[valid].T, dims)
        wv = weights[valid]
        density += np.bincount(flat, weights=wv, minlength=size)
        for c in range(3):
            colour[:, c] += np.bincount(flat, weights=wv * colours[valid, c], minlength=size)

    density = density.reshape(dims).astype(np.float32)
    colour = colour.reshape(*dims, 3).astype(np.float32)
    blurred_weight = ndimage.gaussian_filter(density, COLOUR_SIGMA)[..., None]
    blurred_colour = np.stack([ndimage.gaussian_filter(colour[..., c], COLOUR_SIGMA) for c in range(3)], axis=-1)
    mean_colour = np.clip(blurred_colour / np.maximum(blurred_weight, 1e-6), 0.0, 1.0)
    return SplatGrid(density=density, colour=mean_colour, origin=origin, ceiling=_ceiling_height(xyz[:, 1]), voxel=voxel)


def extract_surface(grid: SplatGrid, iso: float = ISO_LEVEL, smooth_sigma: float = SMOOTH_SIGMA,
                    target_faces: int = TARGET_FACES) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Marching cubes on the smoothed opacity field → (vertices, faces, vertex RGB)."""
    from skimage.measure import marching_cubes
    import fast_simplification
    import trimesh

    voxel = grid.voxel
    field = ndimage.gaussian_filter(grid.density, smooth_sigma)
    cut = int(np.floor((grid.ceiling - CEILING_CLEARANCE - grid.origin[1]) / voxel))
    field[:, max(cut, 0):, :] = 0.0  # open the room from above

    verts, faces, _, _ = marching_cubes(field, level=iso, step_size=1, allow_degenerate=False)
    mesh = trimesh.Trimesh(verts * voxel + grid.origin, faces, process=False)

    component = trimesh.graph.connected_component_labels(mesh.face_adjacency, node_count=len(mesh.faces))
    sizes = np.bincount(component)
    mesh.update_faces(sizes[component] >= MIN_COMPONENT_FACES)
    mesh.remove_unreferenced_vertices()

    if len(mesh.faces) > target_faces:
        v, f = fast_simplification.simplify(
            mesh.vertices.astype(np.float32), mesh.faces.astype(np.int32),
            target_reduction=1.0 - target_faces / len(mesh.faces),
        )
        mesh = trimesh.Trimesh(v, f, process=False)

    coords = ((mesh.vertices - grid.origin) / voxel).T
    rgb = np.stack([ndimage.map_coordinates(grid.colour[..., c], coords, order=1, mode="nearest") for c in range(3)], axis=1)
    return mesh.vertices.astype(np.float32), mesh.faces.astype(np.int32), np.clip(rgb, 0.0, 1.0)


def is_mesh_export(path: Path) -> bool:
    if not path.exists():
        return False
    with open(path, "rb") as handle:
        head = handle.read(512)
    return MESH_MARKER.encode("ascii") in head


def _ceiling_height(heights: np.ndarray) -> float:
    """Highest dense horizontal layer in the upper half: the ceiling.

    The densest upper layer is often the overhead pipe rack, not the ceiling; cutting there removed
    every overhead pipe from the mesh. Take the *highest* layer that is still dense, and never cut
    below the 97th height percentile.
    """
    bins = np.arange(heights.min(), heights.max() + 0.02, 0.02)
    counts, edges = np.histogram(heights, bins=bins)
    half = len(counts) // 2
    upper = counts[half:]
    dense = np.nonzero(upper >= 0.35 * upper.max())[0]
    highest = half + int(dense[-1]) if len(dense) else half + int(np.argmax(upper))
    return float(max(edges[highest], np.percentile(heights, 97)))


def _write_mesh_ply(path: Path, verts: np.ndarray, rgb: np.ndarray, faces: np.ndarray) -> None:
    vertex = np.empty(len(verts), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("red", "u1"), ("green", "u1"), ("blue", "u1")])
    vertex["x"], vertex["y"], vertex["z"] = verts[:, 0], verts[:, 1], verts[:, 2]
    rgb8 = np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
    vertex["red"], vertex["green"], vertex["blue"] = rgb8[:, 0], rgb8[:, 1], rgb8[:, 2]

    face = np.empty(len(faces), dtype=[("n", "u1"), ("i", "<i4", (3,))])
    face["n"] = 3
    face["i"] = faces

    header = "\n".join([
        "ply",
        "format binary_little_endian 1.0",
        MESH_MARKER,
        f"element vertex {len(verts)}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        f"element face {len(faces)}",
        "property list uchar int vertex_indices",
        "end_header",
        "",
    ])
    with open(path, "wb") as handle:
        handle.write(header.encode("ascii"))
        vertex.tofile(handle)
        face.tofile(handle)
