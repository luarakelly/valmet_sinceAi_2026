"""Event-based path briefings: what the robot tells the technician as it passes each mapped asset.

The route is planned once; every mapped asset it passes within PROXIMITY_RADIUS_M gets one short
briefing keyed to the route progress at its closest approach. The viewer plays a briefing when
the robot reaches that progress, so nothing is simulated or timed by hand.
Text comes from the pack's Current_State; Gemini only rephrases it (see FieldServiceCopilot.narrate).
"""

import math
from typing import Any, Dict, List, Tuple

from app.metaverse.copilot import FieldServiceCopilot
from app.metaverse.navigation import PROXIMITY_RADIUS_M, box_edge_distance_m

SAMPLE_STEP_M = 0.1
HEALTHY = "healthy"

Waypoint = Dict[str, float]
Sample = Tuple[float, float, float]  # x, z, metres travelled


def route_samples(waypoints: List[Waypoint]) -> List[Sample]:
    """Points along the route every SAMPLE_STEP_M, with the distance travelled to each."""
    samples: List[Sample] = []
    travelled = 0.0
    for start, end in zip(waypoints, waypoints[1:]):
        length = math.hypot(end["x"] - start["x"], end["z"] - start["z"])
        steps = max(1, int(length / SAMPLE_STEP_M))
        for step in range(steps):
            fraction = step / steps
            x = start["x"] + (end["x"] - start["x"]) * fraction
            z = start["z"] + (end["z"] - start["z"]) * fraction
            samples.append((x, z, travelled + length * fraction))
        travelled += length
    last = waypoints[-1]
    samples.append((last["x"], last["z"], travelled))
    return samples


def find_encounters(frames: List[Dict[str, Any]], waypoints: List[Waypoint]) -> List[Dict[str, Any]]:
    """Frames the route passes within PROXIMITY_RADIUS_M, with route progress (0..1) at closest approach."""
    samples = route_samples(waypoints)
    total = samples[-1][2]
    encounters = []
    for frame in frames:
        edge_distances = [box_edge_distance_m(x, z, frame["pos"], frame["size"]) for x, z, _ in samples]
        closest = min(range(len(samples)), key=edge_distances.__getitem__)
        if edge_distances[closest] > PROXIMITY_RADIUS_M:
            continue
        encounters.append({
            "frame": frame,
            "progress": samples[closest][2] / total,
            "distance_m": edge_distances[closest],
        })
    return sorted(encounters, key=lambda e: e["progress"])


def headline(asset: Dict[str, Any]) -> str:
    """Deterministic one-liner from the pack; the fallback whenever Gemini is off or rejected."""
    state = asset.get("state") or {}
    tag = asset.get("tag")
    health = state.get("health_score")
    if state.get("condition_state") == HEALTHY:
        return f"{tag} is healthy ({health}/100). No action needed."
    return (
        f"{tag}: {state.get('issue_summary')} (health {health}/100, urgency {state.get('urgency')}). "
        f"Next check: {state.get('recommended_next_check')}."
    )


def narration_fields(asset: Dict[str, Any]) -> Dict[str, Any]:
    """The only facts Gemini may use for one asset."""
    state = asset.get("state") or {}
    return {
        "asset_id": asset["asset_id"],
        "tag": asset.get("tag"),
        "asset_class": asset.get("asset_class"),
        "area": asset.get("area_name"),
        "condition_state": state.get("condition_state"),
        "health_score": state.get("health_score"),
        "issue_summary": state.get("issue_summary"),
        "urgency": state.get("urgency"),
        "recommended_next_check": state.get("recommended_next_check"),
    }


def build_briefings(
    frames: List[Dict[str, Any]],
    waypoints: List[Waypoint],
    assets: List[Dict[str, Any]],
    copilot: FieldServiceCopilot,
) -> List[Dict[str, Any]]:
    """One briefing per mapped asset on the route, in walking order."""
    assets_by_id = {asset["asset_id"]: asset for asset in assets}
    encounters = [e for e in find_encounters(frames, waypoints) if e["frame"]["asset_id"] in assets_by_id]
    narration = copilot.narrate([narration_fields(assets_by_id[e["frame"]["asset_id"]]) for e in encounters])

    briefings = []
    for encounter in encounters:
        frame = encounter["frame"]
        asset = assets_by_id[frame["asset_id"]]
        briefings.append({
            "asset_id": frame["asset_id"],
            "tag": frame["tag"],
            "asset_class": frame["class"],
            "state": frame["state"],
            "health": frame["health"],
            "is_target": frame["is_target"],
            "progress": round(encounter["progress"], 4),
            "distance_m": round(encounter["distance_m"], 2),
            "text": narration.get(frame["asset_id"]) or headline(asset),
            "is_generated": frame["asset_id"] in narration,
        })
    return briefings
