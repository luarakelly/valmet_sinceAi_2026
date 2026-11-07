"""Score predicted boxes against operator ground truth: recall at a 3D IoU threshold and label accuracy."""

from dataclasses import dataclass
from typing import List, Optional, Sequence

from infra.labeling.instances import OrientedBox, box_iou

IOU_THRESHOLD = 0.25


@dataclass(frozen=True)
class LabeledBox:
    asset_class: Optional[str]
    box: OrientedBox


def score_boxes(truth: Sequence[LabeledBox], predicted: Sequence[LabeledBox], iou_threshold: float = IOU_THRESHOLD) -> dict:
    """Each truth box is matched to its best-overlapping prediction (a prediction may serve one truth box)."""
    unused = list(range(len(predicted)))
    found = 0
    correctly_labelled = 0
    for wanted in truth:
        best, best_iou = None, 0.0
        for index in unused:
            overlap = box_iou(wanted.box, predicted[index].box)
            if overlap > best_iou:
                best, best_iou = index, overlap
        if best is not None and best_iou >= iou_threshold:
            found += 1
            unused.remove(best)
            if predicted[best].asset_class == wanted.asset_class:
                correctly_labelled += 1
    total = len(truth)
    return {
        "truth": total,
        "found": found,
        "recall": found / total if total else 0.0,
        "label_accuracy": correctly_labelled / found if found else 0.0,
        "iou_threshold": iou_threshold,
    }
