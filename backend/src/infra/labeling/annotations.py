"""Hand-drawn 2D boxes per captured view → validated 3D boxes → merged semantic objects.

Annotations are data (data/view_annotations.json), so the whole result can be regenerated whenever the
scan, the cameras or the thresholds change. Nothing here raises on bad input: every rejected box or view
is returned as an issue with its reason.
"""

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from infra.labeling.instances import OrientedBox, box_iou, fit_box
from infra.labeling.semantic_objects import ID_PREFIX, ROUND_DIGITS, SemanticObject, asset_class_of, points_in_box
from infra.spatial.segmentation import SceneObject
from infra.labeling.vocabulary import VOCABULARY
from sklearn.cluster import DBSCAN

from infra.spatial.placements import nearest_surface_indices, points_in_view_box

KNOWN_LABELS = {term.label for term in VOCABULARY}
MIN_BOX_FRACTION = 0.01
MIN_SIDE_M = 0.03
MAX_SIDE_M = 4.0  # default ceiling for sizes; a bigger box grabbed wall or ceiling
# Largest plausible side per label (m): a box beyond it picked up the wall behind the object or its neighbour.
MAX_SIDE_BY_LABEL = {
    "DOOR": 2.5, "ELECTRICAL_CABINET": 1.3, "PUMP": 0.9, "TANK": 1.8, "CRATE": 1.5, "CHAIR": 1.0,
    "TROLLEY": 1.7, "WASHING_MACHINE": 1.3, "LADDER": 2.2, "PALLET": 1.6, "PIPE": 4.0, "PRESSURE_GAUGE": 0.3,
    "VALVE": 0.8, "VACUUM_CLEANER": 0.9, "TARP": 1.2, "CANISTER": 0.4, "RACK": 2.2, "FIRE_EXTINGUISHER": 1.0,
}
FLOOR_CLEARANCE_M = 0.08  # floor points connect everything standing on it; drop them before clustering
MIN_OBJECT_POINTS = 150
CLUSTER_VOXEL_M = 0.03
CLUSTER_EPS_M = 0.07
CLUSTER_MIN_VOXELS = 6
SNAP_GROWTH = 1.3  # fragments are gathered inside the lifted box grown by this factor
SNAP_MARGIN_M = 0.08
SNAP_MIN_INSIDE = 0.6  # share of a fragment's points that must lie inside to count as part of the item
DUPLICATE_IOU = 0.4
SNAP_MAX_VOLUME_RATIO = 6.0  # the front slab is thin; a whole item is much bigger, but not unboundedly
SURFACE_MIN_SHARE = 0.3  # the object is the nearest surface holding at least this share of the box's points
MERGE_IOU = 0.10
MERGE_CENTER_M = 0.30
REFINE_MARGIN_M = 0.15
REFINE_MIN_POINTS = 60
REFINE_VOLUME_RATIO = (0.8, 1.4)
SCORE_PER_VIEW = 0.25  # confidence grows with the number of views that agree, capped at 1


@dataclass(frozen=True)
class Annotation:
    view_id: str
    label: str
    box: Tuple[float, float, float, float]


@dataclass(frozen=True)
class Candidate:
    view_id: str
    label: str
    box: OrientedBox
    point_count: int


@dataclass
class Report:
    issues: List[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.issues.append(message)


def load_annotations(path: Path, report: Report) -> List[Annotation]:
    """Valid annotations; unreadable file or bad entries are reported, never raised."""
    try:
        views = json.loads(path.read_text())["views"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        report.add("annotations unreadable ({}): {}".format(path.name, error))
        return []
    found: List[Annotation] = []
    for view_id, items in views.items():
        for index, item in enumerate(items):
            problem = _annotation_problem(item)
            if problem:
                report.add("{}[{}] skipped: {}".format(view_id, index, problem))
            else:
                found.append(Annotation(view_id, item["label"], tuple(float(v) for v in item["box"])))
    return found


def lift_annotations(
    xyz: np.ndarray, view_projections: Dict[str, Sequence[float]], annotations: Sequence[Annotation], report: Report
) -> List[Candidate]:
    candidates: List[Candidate] = []
    for annotation in annotations:
        matrix = view_projections.get(annotation.view_id)
        if matrix is None:
            report.add("{} {} skipped: no camera for this view".format(annotation.view_id, annotation.label))
            continue
        lifted = lift_object(xyz, matrix, annotation.box, annotation.label)
        if lifted is None:
            report.add("{} {} skipped: no compact object behind the box".format(annotation.view_id, annotation.label))
            continue
        box, point_count = lifted
        if not _is_plausible_size(box.size, annotation.label):
            report.add("{} {} skipped: implausible size {}".format(annotation.view_id, annotation.label, [round(float(s), 2) for s in box.size]))
            continue
        candidates.append(Candidate(annotation.view_id, annotation.label, box, point_count))
    return candidates


def lift_object(
    xyz: np.ndarray, view_projection: Sequence[float], image_box: Sequence[float], label: str
) -> Optional[Tuple[OrientedBox, int]]:
    """The compact object behind a 2D box: front surface, within the label's size, off the floor, one 3D cluster."""
    depths, points = points_in_view_box(xyz, view_projection, image_box)
    if len(depths) == 0:
        return None
    front_indices = nearest_surface_indices(depths, SURFACE_MIN_SHARE)
    if len(front_indices) == 0:
        return None
    front = depths[front_indices].min()
    depth_reach = MAX_SIDE_BY_LABEL.get(label, MAX_SIDE_M)
    is_candidate = (depths <= front + depth_reach) & (points[:, 1] > FLOOR_CLEARANCE_M)
    cluster = _largest_cluster(points[is_candidate])
    if len(cluster) < MIN_OBJECT_POINTS:
        return None
    return fit_box(cluster), len(cluster)


def _largest_cluster(points: np.ndarray) -> np.ndarray:
    """Points of the biggest spatially connected blob (voxel-thinned first, so it stays fast)."""
    if len(points) == 0:
        return points
    voxels, inverse = np.unique(np.floor(points / CLUSTER_VOXEL_M).astype(np.int64), axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    spots = (voxels + 0.5) * CLUSTER_VOXEL_M
    found = DBSCAN(eps=CLUSTER_EPS_M, min_samples=CLUSTER_MIN_VOXELS).fit_predict(spots)
    if (found >= 0).sum() == 0:
        return points[:0]
    weights = np.bincount(found[found >= 0], minlength=found.max() + 1)
    return points[found[inverse] == int(weights.argmax())]


def merge_candidates(candidates: Sequence[Candidate], xyz: np.ndarray, fragments: Sequence[SceneObject] = ()) -> List[SemanticObject]:
    """One object per physical thing: same-label boxes that overlap are one object seen in several views."""
    objects: List[SemanticObject] = []
    for label in sorted({c.label for c in candidates}):
        groups = _group(sorted((c for c in candidates if c.label == label), key=lambda c: (c.view_id, c.box.center)))
        for number, group in enumerate(groups, start=1):
            objects.append(_object_from(label, number, group, xyz, fragments))
    return _without_duplicates(objects)


def _annotation_problem(item: Dict) -> str:
    try:
        label, (x0, y0, x1, y1) = item["label"], item["box"]
        x0, y0, x1, y1 = float(x0), float(y0), float(x1), float(y1)
    except (KeyError, TypeError, ValueError):
        return "needs a label and a box [x0, y0, x1, y1]"
    if label not in KNOWN_LABELS:
        return "unknown label {!r}".format(label)
    inside = 0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0
    if not inside:
        return "box outside the image or inverted"
    if x1 - x0 < MIN_BOX_FRACTION or y1 - y0 < MIN_BOX_FRACTION:
        return "box too small"
    return ""


def _is_plausible_size(size: Sequence[float], label: str) -> bool:
    largest = MAX_SIDE_BY_LABEL.get(label, MAX_SIDE_M)
    return all(MIN_SIDE_M <= side <= largest for side in size)


def _group(candidates: List[Candidate]) -> List[List[Candidate]]:
    groups: List[List[Candidate]] = []
    for candidate in candidates:
        home = next((g for g in groups if any(_same_thing(candidate.box, member.box) for member in g)), None)
        if home is None:
            groups.append([candidate])
        else:
            home.append(candidate)
    return groups


def _same_thing(a: OrientedBox, b: OrientedBox) -> bool:
    return box_iou(a, b) >= MERGE_IOU or math.dist(a.center, b.center) <= MERGE_CENTER_M


def _object_from(label: str, number: int, group: List[Candidate], xyz: np.ndarray, fragments: Sequence[SceneObject]) -> SemanticObject:
    best_view = max(group, key=lambda c: c.point_count)  # the view that saw the most of the object
    box = _refine(_snap_to_fragments(best_view.box, fragments, label), xyz, label)
    views = {c.view_id for c in group}
    return SemanticObject(
        object_id="{}{}-{:02d}".format(ID_PREFIX, label, number),
        label=label,
        asset_class=asset_class_of(label),
        center=tuple(round(float(v), ROUND_DIGITS) for v in box.center),
        size=tuple(round(float(v), ROUND_DIGITS) for v in box.size),
        yaw=round(float(box.yaw), ROUND_DIGITS),
        point_count=int(sum(c.point_count for c in group)),
        score=round(min(1.0, SCORE_PER_VIEW * len(views)), 2),
        view_count=len(views),
    )


def _snap_to_fragments(box: OrientedBox, fragments: Sequence[SceneObject], label: str) -> OrientedBox:
    """Grow the lifted (front-slab) box to the whole item: union the extracted fragments mostly inside it.

    The extraction already removed walls, floor and ceiling, so the union cannot bleed into them; a fragment
    that sticks far out (a pipe running on) is not mostly inside and stays out.
    """
    window = SceneObject("window", label, box.center, tuple(s * SNAP_GROWTH for s in box.size), 0, (0, 0, 0), yaw=box.yaw)
    reach = MAX_SIDE_BY_LABEL.get(label, MAX_SIDE_M)
    inside = [
        f for f in fragments
        if len(f.points) > 0 and max(f.size) <= reach and points_in_box(f.points, window, SNAP_MARGIN_M).mean() >= SNAP_MIN_INSIDE
    ]
    if not inside:
        return box
    union = np.vstack([f.points for f in inside]).astype(np.float64)
    if len(union) < MIN_OBJECT_POINTS:
        return box
    fitted = fit_box(union)
    is_reasonable_growth = np.prod(fitted.size) <= SNAP_MAX_VOLUME_RATIO * np.prod(box.size)
    if _is_plausible_size(fitted.size, label) and is_reasonable_growth:
        return fitted
    return box


def _without_duplicates(objects: List[SemanticObject]) -> List[SemanticObject]:
    """Two same-label objects whose whole-item boxes overlap strongly are one item seen from different spots."""
    kept: List[SemanticObject] = []
    for obj in sorted(objects, key=lambda o: -o.view_count):
        box = OrientedBox(obj.center, obj.size, obj.yaw)
        twin = next((k for k in kept if k.label == obj.label and box_iou(box, OrientedBox(k.center, k.size, k.yaw)) >= DUPLICATE_IOU), None)
        if twin is None:
            kept.append(obj)
    return kept


def _refine(box: OrientedBox, xyz: np.ndarray, label: str) -> OrientedBox:
    """Fit an oriented box to every scan point near the lifted one (all faces, not just the front slab)."""
    low = np.array(box.center) - np.array(box.size) / 2.0 - REFINE_MARGIN_M
    high = np.array(box.center) + np.array(box.size) / 2.0 + REFINE_MARGIN_M
    near = xyz[((xyz >= low) & (xyz <= high)).all(axis=1)]
    if len(near) < REFINE_MIN_POINTS:
        return box
    fitted = fit_box(near)
    ratio = np.prod(fitted.size) / max(np.prod(box.size), 1e-9)
    if REFINE_VOLUME_RATIO[0] <= ratio <= REFINE_VOLUME_RATIO[1] and _is_plausible_size(fitted.size, label):
        return fitted
    return box
