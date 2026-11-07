"""Procedural binding of builder-pack assets to extracted scene objects.

The brief allows non-physical mapping; this one is still plausible and explainable:
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

from app.metaverse.segmentation import SceneObject

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


@dataclass(frozen=True)
class Binding:
    asset: Dict[str, Any]
    confidence: float


def choose_target(assets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The pre-determined faulty device: lowest health score in Current_State."""
    return min(assets, key=lambda a: (a.get("state") or {}).get("health_score", 100))


def bind_assets(
    objects: List[SceneObject],
    assets: List[Dict[str, Any]],
    target_asset_id: str,
    reach: Dict[str, float],
    walk: Dict[str, float],
) -> Dict[str, Binding]:
    """Return object_id → Binding.

    reach: object_id → metres from the object to its nearest reachable standing cell.
    walk:  object_id → walking metres from the entry to that standing cell.
    """
    eligible = [o for o in objects if reach.get(o.object_id, math.inf) <= REACH_M]
    taken: Dict[str, Binding] = {}

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

    def place(asset: Dict[str, Any], far_first: bool) -> None:
        asset_class = asset.get("asset_class", "")
        free = [o for o in eligible if o.object_id not in taken]
        if not free:
            return

        def sort_key(obj: SceneObject):
            if far_first:
                return (rank(obj, asset_class), -walk.get(obj.object_id, 0.0), obj.object_id)
            return (rank(obj, asset_class), -round(spread(obj), 2), obj.object_id)

        best = min(free, key=sort_key)
        best_rank = rank(best, asset_class)
        if best_rank < len(CONFIDENCE_BY_RANK):
            confidence = CONFIDENCE_BY_RANK[best_rank]
        else:
            confidence = FALLBACK_CONFIDENCE
        taken[best.object_id] = Binding(asset=asset, confidence=confidence)

    target = _find(assets, target_asset_id)
    if target is not None:
        place(target, far_first=True)

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
