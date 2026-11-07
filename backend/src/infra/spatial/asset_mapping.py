"""Binding of builder-pack assets to extracted scene objects.

The workbook has no real positions (Scene_Anchors are placeholders on a 30 x 15 m grid; the scan
room is about 8 x 3 m), so identity has to come from evidence in the scan:
- camera-verified: a vision-language model looked at a render of the object and said what it is
  (see VerificationService). Only objects verified as the asset's class are eligible, best first;
- proposed: objects nobody has looked at yet fall back to shape-based guessing, with low confidence;
- an asset with no verified or unverified candidate stays unlocated, except the inspection target,
  which is placed on the nearest reachable object ("assumed") so the route demo can still run.

The shape-based guess works like this:
- each asset class prefers geometric labels that look like it (pumps → floor machines, ...);
- only objects with a free standing spot within REACH_M are eligible, so every asset is serviceable;
- the inspection target is placed first, on the best-matching object with the longest walk from
  the entry, so the robot crosses the room and passes as much equipment as possible;
- the other assets are spread out (farthest-point placement among equally good objects), so the
  nearby-assets display changes along the walk instead of showing one dense cluster;
- mapping_confidence drops with each step down the preference list (trustworthy-AI requirement).
"""

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional, Tuple

from infra.spatial.segmentation import SceneObject

REACH_M = 0.9
FALLBACK_CONFIDENCE = 0.4

PREFERENCES: Dict[str, Tuple[str, ...]] = {
    "PROCESS_PUMP": ("FLOOR_MOUNTED_MACHINE", "EQUIPMENT_RACK", "VALVE_ASSEMBLY"),
    "ELECTRIC_MOTOR": ("FLOOR_MOUNTED_MACHINE", "EQUIPMENT_RACK", "VALVE_ASSEMBLY"),
    "CONTROL_VALVE": ("VALVE_HANDWHEEL", "VALVE_ASSEMBLY", "HORIZONTAL_PIPE_RUN"),
    "PRESSURE_TRANSMITTER": ("FIELD_INSTRUMENT", "VALVE_ASSEMBLY"),
    "VIBRATION_SENSOR": ("FIELD_INSTRUMENT", "VALVE_ASSEMBLY"),
}
CONFIDENCE_BY_RANK = (0.85, 0.7, 0.55)

# Scarce object types first so plentiful ones (valves) cannot crowd them out.
CLASS_ORDER = ("PROCESS_PUMP", "ELECTRIC_MOTOR", "PRESSURE_TRANSMITTER", "VIBRATION_SENSOR", "CONTROL_VALVE")


CAMERA_VERIFIED = "camera_verified"
PROPOSED = "proposed"
ASSUMED = "assumed"

MAX_VERIFIED_CONFIDENCE = 0.95
PROPOSED_CONFIDENCE_CAP = 0.45  # once camera evidence exists, an unlooked-at object is only a guess
ASSUMED_CONFIDENCE = 0.2


@dataclass(frozen=True)
class Verified:
    """What the camera check said an object is. asset_class None = visible but not a pack asset class."""

    category: str
    asset_class: Optional[str]
    confidence: float
    features: str = ""


@dataclass(frozen=True)
class Binding:
    asset: Dict[str, Any]
    confidence: float
    status: str = PROPOSED
    evidence: str = ""


def choose_target(assets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The pre-determined faulty device: lowest health score in Current_State."""
    return min(assets, key=lambda a: (a.get("state") or {}).get("health_score", 100))


def bind_assets(
    objects: List[SceneObject],
    assets: List[Dict[str, Any]],
    target_asset_id: str,
    reach: Dict[str, float],
    walk: Dict[str, float],
    verified: Optional[Dict[str, Verified]] = None,
) -> Dict[str, Binding]:
    """Return object_id → Binding.

    reach: object_id → metres from the object to its nearest reachable standing cell.
    walk:  object_id → walking metres from the entry to that standing cell.
    verified: object_id → camera verification result (empty/None = nothing verified yet).
    """
    verified = verified or {}
    eligible = [o for o in objects if reach.get(o.object_id, math.inf) <= REACH_M]
    taken: Dict[str, Binding] = {}

    def looks_like(obj: SceneObject, asset_class: str) -> Optional[bool]:
        """True/False once the camera has looked at the object, None if it has not."""
        seen = verified.get(obj.object_id)
        return None if seen is None else seen.asset_class == asset_class

    def rank(obj: SceneObject, asset_class: str) -> int:
        preferences = PREFERENCES.get(asset_class, ())
        if obj.label in preferences:
            return preferences.index(obj.label)
        return len(preferences)

    def spread(obj: SceneObject) -> float:
        """Horizontal distance to the nearest already-bound object (larger = more spread out)."""
        if not taken:
            return math.inf
        by_id = {o.object_id: o for o in eligible}
        return min(
            math.hypot(obj.center[0] - by_id[oid].center[0], obj.center[2] - by_id[oid].center[2])
            for oid in taken
        )

    def place(asset: Dict[str, Any], far_first: bool, is_target: bool = False) -> None:
        asset_class = asset.get("asset_class", "")
        free = [o for o in eligible if o.object_id not in taken]
        confirmed = [o for o in free if looks_like(o, asset_class) is True]
        unseen = [o for o in free if looks_like(o, asset_class) is None]
        if confirmed:
            pool, status = confirmed, CAMERA_VERIFIED
        elif unseen:
            pool, status = unseen, PROPOSED
        elif is_target and free:
            pool, status = free, ASSUMED
        else:
            return  # no object that is, or might be, this asset: leave it unlocated

        def sort_key(obj: SceneObject):
            certainty = -round(verified[obj.object_id].confidence, 1) if status == CAMERA_VERIFIED else 0.0
            if far_first:
                return (certainty, rank(obj, asset_class), -walk.get(obj.object_id, 0.0), obj.object_id)
            return (certainty, rank(obj, asset_class), -round(spread(obj), 2), obj.object_id)

        best = min(pool, key=sort_key)
        if status == CAMERA_VERIFIED:
            seen = verified[best.object_id]
            confidence = min(MAX_VERIFIED_CONFIDENCE, seen.confidence)
            evidence = "Camera check: looks like {} ({:.2f})".format(seen.features or seen.category, seen.confidence)
        elif status == PROPOSED:
            best_rank = rank(best, asset_class)
            confidence = CONFIDENCE_BY_RANK[best_rank] if best_rank < len(CONFIDENCE_BY_RANK) else FALLBACK_CONFIDENCE
            if verified:
                confidence = min(confidence, PROPOSED_CONFIDENCE_CAP)
            evidence = "Shape-based guess, not verified by camera"
        else:
            confidence = ASSUMED_CONFIDENCE
            evidence = "No camera-verified match; placed on the nearest reachable object so the route can run"
        taken[best.object_id] = Binding(asset=asset, confidence=round(confidence, 2), status=status, evidence=evidence)

    target = _find(assets, target_asset_id)
    if target is not None:
        place(target, far_first=True, is_target=True)

    for asset_class in CLASS_ORDER:
        for asset in assets:
            if asset.get("asset_class") == asset_class and asset.get("asset_id") != target_asset_id:
                place(asset, far_first=False)
    return taken


def _find(assets: List[Dict[str, Any]], asset_id: str) -> Optional[Dict[str, Any]]:
    for asset in assets:
        if asset.get("asset_id") == asset_id:
            return asset
    return None
