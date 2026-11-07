"""Views with 2D detections → labelled, oriented 3D boxes (back-project, vote across views, DBSCAN, fit)."""

from dataclasses import dataclass
from typing import Iterable, List, Sequence

import numpy as np

from infra.labeling.backprojection import points_in_masks
from infra.labeling.fusion import NO_LABEL, LabelVotes, add_view_masks
from infra.labeling.instances import cluster_instances, fit_box
from infra.labeling.segmenter import Detection
from infra.labeling.semantic_objects import ID_PREFIX, ROUND_DIGITS, SemanticObject, asset_class_of
from infra.labeling.vocabulary import VOCABULARY


@dataclass(frozen=True)
class ViewDetections:
    view_projection: Sequence[float]
    detections: List[Detection]


def build_semantic_objects(xyz: np.ndarray, views: Iterable[ViewDetections]) -> List[SemanticObject]:
    labels = [term.label for term in VOCABULARY]
    votes = LabelVotes.empty(len(xyz), len(labels))
    for view in views:
        hits = points_in_masks(xyz, view.view_projection, [d.mask for d in view.detections])
        add_view_masks(votes, [(h, labels.index(d.term.label), d.score) for h, d in zip(hits, view.detections)])
    assigned = votes.assign()
    objects: List[SemanticObject] = []
    for label_index, label in enumerate(labels):
        objects.extend(_objects_for_label(xyz, votes, assigned, label_index, label))
    return objects


def _objects_for_label(xyz: np.ndarray, votes: LabelVotes, assigned: np.ndarray, label_index: int, label: str) -> List[SemanticObject]:
    indices = np.flatnonzero(assigned == label_index)
    found: List[SemanticObject] = []
    for number, cluster in enumerate(cluster_instances(xyz[indices]), start=1):
        member = indices[cluster]
        box = fit_box(xyz[member])
        views = votes.views[member, label_index]
        found.append(SemanticObject(
            object_id="{}{}-{:02d}".format(ID_PREFIX, label, number),
            label=label,
            asset_class=asset_class_of(label),
            center=tuple(round(v, ROUND_DIGITS) for v in box.center),
            size=tuple(round(v, ROUND_DIGITS) for v in box.size),
            yaw=round(box.yaw, ROUND_DIGITS),
            point_count=int(len(member)),
            score=round(float((votes.score[member, label_index] / views).mean()), 2),
            view_count=int(np.median(views)),
        ))
    return found
