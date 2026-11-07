"""data/semantic_objects.json: labelled oriented boxes, and their merge into the geometric scene."""

from dataclasses import asdict, dataclass
import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from infra.labeling.vocabulary import VOCABULARY
from infra.spatial.asset_mapping import Verified
from infra.spatial.segmentation import SceneObject

logger = logging.getLogger("ask_your_factory.semantic")

SCHEMA_VERSION = 1
ID_PREFIX = "SEM-"
COVERED_FRACTION = 0.5  # a geometric object this far inside a semantic box is the same thing
BOX_MARGIN_M = 0.05
NEUTRAL_COLOR = (0.5, 0.5, 0.5)
ROUND_DIGITS = 3


@dataclass(frozen=True)
class SemanticObject:
    object_id: str
    label: str
    asset_class: Optional[str]
    center: Tuple[float, float, float]
    size: Tuple[float, float, float]
    yaw: float
    point_count: int
    score: float
    view_count: int


def asset_class_of(label: str) -> Optional[str]:
    for term in VOCABULARY:
        if term.label == label:
            return term.asset_class
    return None


def write_semantic_objects(path: Path, objects: List[SemanticObject]) -> None:
    payload = {"version": SCHEMA_VERSION, "objects": [asdict(obj) for obj in objects]}
    path.write_text(json.dumps(payload, indent=1))


def read_semantic_objects(path: Path) -> List[SemanticObject]:
    """Objects from disk; an absent or malformed file means none (the server must still start)."""
    if not path.exists():
        return []
    try:
        records = json.loads(path.read_text())["objects"]
        return [_from_record(record) for record in records]
    except (OSError, ValueError, KeyError, TypeError) as error:
        logger.warning("Ignoring unreadable %s: %s", path.name, error)
        return []


def _from_record(record: Dict) -> SemanticObject:
    return SemanticObject(
        object_id=str(record["object_id"]),
        label=str(record["label"]),
        asset_class=record.get("asset_class"),
        center=tuple(float(v) for v in record["center"]),
        size=tuple(float(v) for v in record["size"]),
        yaw=float(record.get("yaw", 0.0)),
        point_count=int(record["point_count"]),
        score=float(record.get("score", 0.0)),
        view_count=int(record.get("view_count", 0)),
    )


def to_scene_object(obj: SemanticObject) -> SceneObject:
    return SceneObject(
        object_id=obj.object_id,
        label=obj.label,
        center=obj.center,
        size=obj.size,
        point_count=obj.point_count,
        color=NEUTRAL_COLOR,
        yaw=obj.yaw,
    )


def merge_semantic(
    geometric: List[SceneObject], semantic: List[SemanticObject]
) -> Tuple[List[SceneObject], Dict[str, Verified]]:
    """Semantic objects replace the geometric ones they cover; asset classes become camera-style evidence."""
    scene_semantic = [to_scene_object(obj) for obj in semantic]
    kept = [obj for obj in geometric if not _is_covered(obj, scene_semantic)]
    verified: Dict[str, Verified] = {}
    for obj in semantic:
        verified[obj.object_id] = Verified(
            category=obj.label.lower().replace("_", " "),
            asset_class=obj.asset_class,
            confidence=obj.score,
            features="{} views agree".format(obj.view_count),
        )
    return kept + scene_semantic, verified


def points_in_box(points: np.ndarray, obj: SceneObject, margin: float = BOX_MARGIN_M) -> np.ndarray:
    """Boolean per point: inside the yawed box grown by `margin`."""
    offset = points - np.array(obj.center)
    c, s = math.cos(obj.yaw), math.sin(obj.yaw)
    along = offset[:, 0] * c + offset[:, 2] * s
    across = -offset[:, 0] * s + offset[:, 2] * c
    half = np.array(obj.size) / 2.0 + margin
    return (np.abs(along) <= half[0]) & (np.abs(offset[:, 1]) <= half[1]) & (np.abs(across) <= half[2])


def _is_covered(obj: SceneObject, boxes: List[SceneObject]) -> bool:
    if len(obj.points) == 0:
        return False
    return any(points_in_box(obj.points, box).mean() >= COVERED_FRACTION for box in boxes)
