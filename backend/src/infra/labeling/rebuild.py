"""Regenerate data/semantic_objects.json from annotations (+ optional model output), with safety gates."""

from dataclasses import dataclass
from typing import Dict, List, Sequence

import numpy as np

from infra.labeling.annotations import Report, lift_annotations, load_annotations, merge_candidates
from infra.labeling.instances import OrientedBox, box_iou
from infra.labeling.semantic_objects import SemanticObject
from infra.spatial.segmentation import Room
from pathlib import Path

ROOM_MARGIN_M = 0.3  # an object centre further outside the room than this is a back-projection error
MODEL_OVERLAP_IOU = 0.15


@dataclass(frozen=True)
class RebuildResult:
    objects: List[SemanticObject]
    issues: List[str]


def rebuild_objects(
    xyz: np.ndarray,
    room: Room,
    view_projections: Dict[str, Sequence[float]],
    annotations_path: Path,
    model_objects: Sequence[SemanticObject],
) -> RebuildResult:
    report = Report()
    annotations = load_annotations(annotations_path, report)
    candidates = lift_annotations(xyz, view_projections, annotations, report)
    drawn = merge_candidates(candidates, xyz)
    combined = drawn + _model_only(model_objects, drawn)
    inside = [_clamped_to_height(obj, room) for obj in combined if _is_inside_room(obj, room, report)]
    return RebuildResult(_renumber(inside), report.issues)


def _model_only(model: Sequence[SemanticObject], drawn: Sequence[SemanticObject]) -> List[SemanticObject]:
    """Model detections add to the hand-drawn boxes; they never override or duplicate them."""
    return [obj for obj in model if not any(_overlaps(obj, other) for other in drawn)]


def _overlaps(a: SemanticObject, b: SemanticObject) -> bool:
    return box_iou(OrientedBox(a.center, a.size, a.yaw), OrientedBox(b.center, b.size, b.yaw)) >= MODEL_OVERLAP_IOU


def _is_inside_room(obj: SemanticObject, room: Room, report: Report) -> bool:
    x, y, z = obj.center
    inside = (
        room.x_min - ROOM_MARGIN_M <= x <= room.x_max + ROOM_MARGIN_M
        and room.z_min - ROOM_MARGIN_M <= z <= room.z_max + ROOM_MARGIN_M
        and -ROOM_MARGIN_M <= y <= room.ceiling + ROOM_MARGIN_M
    )
    if not inside:
        report.add("{} dropped: centre {} is outside the room".format(obj.object_id, [round(v, 2) for v in obj.center]))
    return inside


def _clamped_to_height(obj: SemanticObject, room: Room) -> SemanticObject:
    """Nothing stands below the floor or above the ceiling: trim the box instead of trusting stray splats."""
    bottom = round(max(0.0, obj.center[1] - obj.size[1] / 2.0), 2)
    top = round(min(room.ceiling, obj.center[1] + obj.size[1] / 2.0), 2)
    if top - bottom <= 0:
        return obj
    centre = (obj.center[0], round((bottom + top) / 2.0, 3), obj.center[2])  # 2-decimal ends keep the 3-decimal centre exact
    size = (obj.size[0], round(top - bottom, 3), obj.size[2])
    return SemanticObject(obj.object_id, obj.label, obj.asset_class, centre, size, obj.yaw, obj.point_count, obj.score, obj.view_count)


def _renumber(objects: List[SemanticObject]) -> List[SemanticObject]:
    """Stable ids: label + running number in a fixed order, so reruns give identical files."""
    ordered = sorted(objects, key=lambda o: (o.label, o.center))
    counts: Dict[str, int] = {}
    renumbered = []
    for obj in ordered:
        counts[obj.label] = counts.get(obj.label, 0) + 1
        renumbered.append(SemanticObject(
            "SEM-{}-{:02d}".format(obj.label, counts[obj.label]), obj.label, obj.asset_class, obj.center,
            obj.size, obj.yaw, obj.point_count, obj.score, obj.view_count,
        ))
    return renumbered
