"""Maintenance prioritisation: condition × criticality × urgency × model certainty (builder question Q-04)."""

from typing import Any, Dict, List

from business.interfaces.ports.outbound import AssetRepository
from business.services.scene_service import SceneService

STATE_WEIGHT = {"attention_required": 1.0, "degraded": 0.7, "watch": 0.4, "healthy": 0.0}
URGENCY_WEIGHT = {"high": 1.0, "medium": 0.6, "routine": 0.2, "low": 0.2}
CRITICALITY_WEIGHT = {"A": 1.0, "B": 0.7, "C": 0.45}


class MaintenanceService:
    def __init__(self, assets: AssetRepository, scene: SceneService):
        self._assets = assets
        self._scene = scene

    def priorities(self, limit: int = 10, attention_only: bool = True) -> List[Dict[str, Any]]:
        assets = {a["asset_id"]: a for a in self._assets.list()}
        ranked = []
        for asset_id, state in self._assets.states().items():
            asset = assets.get(asset_id)
            if asset is None:
                continue
            condition = max(0.0, (100.0 - float(state["health_score"])) / 100.0)
            state_weight = STATE_WEIGHT.get(state["condition_state"], 0.3)
            if attention_only and state_weight == 0.0:
                continue
            urgency = URGENCY_WEIGHT.get((state.get("urgency") or "").lower(), 0.3)
            criticality = CRITICALITY_WEIGHT.get((asset.get("criticality") or "C").strip()[:1].upper(), 0.45)
            certainty = float(state.get("model_confidence") or 0.5)
            score = (0.45 * condition + 0.35 * state_weight + 0.2 * urgency) * criticality * (0.6 + 0.4 * certainty)
            frame = self._scene.find_frame(asset_id)
            ranked.append({
                "asset_id": asset_id,
                "tag": asset["tag"],
                "asset_class": asset["asset_class"],
                "health_score": state["health_score"],
                "condition_state": state["condition_state"],
                "issue_code": state.get("issue_code"),
                "issue_summary": state.get("issue_summary"),
                "urgency": state.get("urgency"),
                "criticality": asset.get("criticality") or "",
                "score": round(score, 3),
                "reasons": [
                    "condition '{}' with health {:.0f}".format(state["condition_state"], state["health_score"]),
                    "criticality {}".format(asset.get("criticality")),
                    "urgency {}".format(state.get("urgency")),
                    "model confidence {:.2f}".format(certainty),
                ],
                "scene_object_id": frame["scene_id"] if frame and frame.get("asset_id") == asset_id else None,
            })
        ranked.sort(key=lambda item: (-item["score"], item["asset_id"]))
        for rank, item in enumerate(ranked[:limit], start=1):
            item["rank"] = rank
        return ranked[:limit]
