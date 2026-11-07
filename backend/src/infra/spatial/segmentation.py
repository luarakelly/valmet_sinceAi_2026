"""Semantic object extraction from the canonical boiler-room cloud.

Pipeline (pure NumPy/SciPy, < 1 s):
1. Room footprint from robust XZ extents; points hugging the walls, floor and ceiling are removed.
2. Two height layers are voxelised separately: equipment (floor → pipe rack) and overhead (pipe rack).
3. 26-connected voxel components are split recursively until each fits an object-sized box:
   first at thin connections (erosion seeds + nearest-seed regrowth), then at the sparsest plane.
4. Each box is labelled from geometry (size, elongation, height) and dominant colour.
"""

from dataclasses import dataclass
from typing import Iterator, List, Tuple

import numpy as np
from scipy import ndimage

from infra.spatial.point_cloud import PointCloud

VOXEL = 0.04
MIN_POINTS_PER_VOXEL = 2
MIN_OBJECT_VOXELS = 10
MAX_OBJECT_EXTENT = 0.8
MAX_EROSION = 4
PIPE_MAX_DIAMETER = 0.3
WALL_BAND = 0.10
FLOOR_BAND = 0.06
CEILING_BAND = 0.08
PIPE_RACK_HEIGHT = 1.7
ROOM_CELL = 0.1
ROOM_MIN_CELL_POINTS = 25
ROOM_PERCENTILES = (0.5, 99.5)
CEILING_PERCENTILE = 99.0

NEIGHBOURS_26 = np.ones((3, 3, 3), dtype=bool)


@dataclass(frozen=True)
class Room:
    """Axis-aligned room envelope in the canonical frame."""

    x_min: float
    x_max: float
    z_min: float
    z_max: float
    ceiling: float


@dataclass(frozen=True)
class SceneObject:
    """One extracted, framed object: axis-aligned box plus geometric label."""

    object_id: str
    label: str
    center: Tuple[float, float, float]
    size: Tuple[float, float, float]
    point_count: int
    color: Tuple[float, float, float]


def detect_room(cloud: PointCloud) -> Room:
    """Footprint = robust extent of dense XZ cells (stray splats form sparse rays and spikes)."""
    xz = cloud.xyz[:, [0, 2]]
    origin = xz.min(axis=0)
    cells = np.floor((xz - origin) / ROOM_CELL).astype(int)
    density = np.zeros(cells.max(axis=0) + 1, dtype=np.int32)
    np.add.at(density, tuple(cells.T), 1)

    dense = origin + (np.argwhere(density >= ROOM_MIN_CELL_POINTS) + 0.5) * ROOM_CELL
    low = np.percentile(dense, ROOM_PERCENTILES[0], axis=0)
    high = np.percentile(dense, ROOM_PERCENTILES[1], axis=0)
    ceiling = float(np.percentile(cloud.xyz[:, 1], CEILING_PERCENTILE))
    return Room(float(low[0]), float(high[0]), float(low[1]), float(high[1]), ceiling)


def extract_objects(cloud: PointCloud, room: Room) -> List[SceneObject]:
    """Segment the cloud into framed objects, ordered by height layer then position."""
    xyz = cloud.xyz
    inner = (
        (xyz[:, 0] > room.x_min + WALL_BAND) & (xyz[:, 0] < room.x_max - WALL_BAND)
        & (xyz[:, 2] > room.z_min + WALL_BAND) & (xyz[:, 2] < room.z_max - WALL_BAND)
    )
    height = xyz[:, 1]
    layers = [
        inner & (height > FLOOR_BAND) & (height < PIPE_RACK_HEIGHT),
        inner & (height >= PIPE_RACK_HEIGHT) & (height < room.ceiling - CEILING_BAND),
    ]

    objects: List[SceneObject] = []
    for layer in layers:
        for lo, hi, points in _segment_layer(xyz[layer], cloud.rgb[layer]):
            objects.append(_describe(len(objects) + 1, lo, hi, points))
    return objects


def _segment_layer(xyz: np.ndarray, rgb: np.ndarray) -> Iterator[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Yield (box_min, box_max, member_rgb) per object found in one height layer."""
    if len(xyz) == 0:
        return
    origin = xyz.min(axis=0)
    index = np.floor((xyz - origin) / VOXEL).astype(int)
    counts = np.zeros(index.max(axis=0) + 1, dtype=np.int32)
    np.add.at(counts, tuple(index.T), 1)

    occupied = ndimage.binary_closing(counts >= MIN_POINTS_PER_VOXEL)
    labels, _ = ndimage.label(occupied, NEIGHBOURS_26)
    for label, region in enumerate(ndimage.find_objects(labels), start=1):
        offset = np.array([s.start for s in region])
        for mask, part_offset in _split(labels[region] == label, offset):
            voxels = np.argwhere(mask) + part_offset
            lo = origin + voxels.min(axis=0) * VOXEL
            hi = origin + (voxels.max(axis=0) + 1) * VOXEL
            members = ((xyz >= lo) & (xyz <= hi)).all(axis=1)
            yield lo, hi, rgb[members]


def _split(mask: np.ndarray, offset: np.ndarray) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
    """Recursively split a voxel mask until every part fits MAX_OBJECT_EXTENT."""
    if mask.sum() < MIN_OBJECT_VOXELS:
        return
    if max(mask.shape) * VOXEL <= MAX_OBJECT_EXTENT:
        yield mask, offset
        return

    parts = _split_at_thin_links(mask)
    if parts is None and not _is_pipe_like(mask):
        parts = _split_at_sparsest_plane(mask)
    if parts is None:
        yield mask, offset
        return

    part_labels, count = parts
    for label, region in enumerate(ndimage.find_objects(part_labels, max_label=count), start=1):
        if region is None:
            continue
        sub_offset = offset + np.array([s.start for s in region])
        yield from _split(part_labels[region] == label, sub_offset)


def _is_pipe_like(mask: np.ndarray) -> bool:
    """Long and thin in two axes: keep whole rather than chopping a pipe into fittings."""
    dims = sorted(mask.shape)
    return dims[1] * VOXEL <= PIPE_MAX_DIAMETER


def _split_at_thin_links(mask: np.ndarray):
    """Erode until the mask falls apart, then regrow each seed over the original voxels."""
    for iterations in range(1, MAX_EROSION + 1):
        seeds, count = ndimage.label(ndimage.binary_erosion(mask, NEIGHBOURS_26, iterations=iterations), NEIGHBOURS_26)
        if count > 1:
            _, nearest = ndimage.distance_transform_edt(seeds == 0, return_indices=True)
            return seeds[tuple(nearest)] * mask, count
        if count == 0:
            return None
    return None


def _split_at_sparsest_plane(mask: np.ndarray):
    """Cut the longest axis where the fewest voxels cross (searching the middle 60 %)."""
    axis = int(np.argmax(mask.shape))
    length = mask.shape[axis]
    other_axes = tuple(a for a in range(3) if a != axis)
    profile = mask.sum(axis=other_axes)
    start = max(1, int(length * 0.2))
    stop = min(length - 1, int(length * 0.8))
    if stop <= start:
        return None
    cut = start + int(np.argmin(profile[start:stop]))

    parts = np.zeros(mask.shape, dtype=np.int32)
    before = [slice(None)] * 3
    before[axis] = slice(0, cut)
    after = [slice(None)] * 3
    after[axis] = slice(cut, None)
    parts[tuple(before)] = mask[tuple(before)] * 1
    parts[tuple(after)] = mask[tuple(after)] * 2
    return parts, 2


def _describe(number: int, lo: np.ndarray, hi: np.ndarray, member_rgb: np.ndarray) -> SceneObject:
    size = hi - lo
    center = (lo + hi) / 2.0
    if len(member_rgb):
        color = member_rgb.mean(axis=0)
    else:
        color = np.full(3, 0.5)
    return SceneObject(
        object_id=f"OBJ-{number:03d}",
        label=classify(center, size, color),
        center=tuple(round(float(v), 3) for v in center),
        size=tuple(round(float(v), 3) for v in size),
        point_count=len(member_rgb),
        color=tuple(round(float(v), 3) for v in color),
    )


def classify(center: np.ndarray, size: np.ndarray, color: np.ndarray) -> str:
    """Geometric + colour heuristics; first match wins, most specific rules first."""
    width, height, depth = (float(v) for v in size)
    footprint_long = max(width, depth)
    footprint_short = max(min(width, depth), 1e-3)
    bottom = float(center[1]) - height / 2
    red, green, blue = (float(v) for v in color)

    if red > 0.5 and red > 1.6 * green and red > 1.6 * blue and footprint_long < 0.5:
        return "FIRE_SAFETY_EQUIPMENT"
    if green > 0.45 and green > 1.3 * red and green > 1.3 * blue:
        return "VALVE_HANDWHEEL"
    if bottom >= PIPE_RACK_HEIGHT:
        if footprint_long / footprint_short > 3:
            return "OVERHEAD_PIPE_RUN"
        return "OVERHEAD_PIPE_FITTING"
    if height > 1.0 and footprint_long < 0.35:
        return "VERTICAL_PIPE_RISER"
    if footprint_long / footprint_short > 4 and height < 0.4:
        return "HORIZONTAL_PIPE_RUN"
    if max(width, height, depth) < 0.3:
        return "FIELD_INSTRUMENT"
    if bottom < 0.25 and footprint_long > 0.4:
        return "FLOOR_MOUNTED_MACHINE"
    if height > 1.0:
        return "EQUIPMENT_RACK"
    return "VALVE_ASSEMBLY"
