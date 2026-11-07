"""Asset use cases: catalogue, 360° detail and evidence lists (builder-pack API_Contract)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from business.errors import NotFoundError
from business.interfaces.ports.outbound import AssetRepository
from business.models.records import AssetRecord
from business.services.scene_service import SceneService

GUIDANCE_DOCS = ("DOC-FIELD-SAFETY", "DOC-RAG-GUIDE", "DOC-3D-MAPPING")


class AssetService:
    def __init__(self, assets: AssetRepository, scene: SceneService):
        self._assets = assets
        self._scene = scene

    def resolve(self, identifier: str) -> AssetRecord:
        asset = self._assets.find(identifier.strip())
        if asset is None:
            raise NotFoundError("Asset with identifier '{}' not found in asset registry.".format(identifier))
        return asset

    def list_assets(
        self,
        area_id: Optional[str] = None,
        asset_class: Optional[str] = None,
        criticality: Optional[str] = None,
        condition_state: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Assets with their current state and scene anchor."""
        assets = self._assets.list(area_id, asset_class, criticality, search)
        states = self._assets.states([a["asset_id"] for a in assets])
        result = []
        for asset in assets:
            state = states.get(asset["asset_id"])
            if condition_state and state and state["condition_state"].lower() != condition_state.strip().lower():
                continue
            result.append({**asset, "current_state": state, "state": state, "anchor": self._scene.anchor(asset["asset_id"], state)})
        return result

    def detail(self, identifier: str) -> Dict[str, Any]:
        asset = self.resolve(identifier)
        asset_id = asset["asset_id"]
        state = self._assets.states([asset_id]).get(asset_id)
        doc_ids = [state["knowledge_doc_id"]] if state and state.get("knowledge_doc_id") else []
        docs = self._assets.documents(doc_ids, scopes=(asset["asset_class"], "ALL"))
        work_orders = self._assets.work_orders(asset_id, 5)
        return {
            **asset,
            "current_state": state,
            "state": state,
            "anchor": self._scene.anchor(asset_id, state),
            "recent_telemetry": self._assets.recent_telemetry(asset_id, 10),
            "recent_events": self._assets.events(asset_id, 10),
            "maintenance_history": work_orders,
            "work_orders": work_orders,
            "knowledge_docs": docs,
            "knowledge_doc": docs[0] if docs else None,
            "data_quality_issues": self._assets.data_quality(asset_id),
        }

    def telemetry(self, identifier: str, limit: int, start: Optional[datetime], end: Optional[datetime]):
        return self._assets.telemetry_range(self.resolve(identifier)["asset_id"], limit, start, end)

    def events(self, identifier: str, limit: int, severity=None, event_type=None, status=None):
        return self._assets.events(self.resolve(identifier)["asset_id"], limit, severity, event_type, status)

    def documents(self, identifier: str) -> List[Dict[str, Any]]:
        """Asset-specific guidance + class guidance + mandatory safety/RAG/3D-mapping docs."""
        asset = self.resolve(identifier)
        state = self._assets.states([asset["asset_id"]]).get(asset["asset_id"])
        doc_ids = []
        if state and state.get("knowledge_doc_id"):
            doc_ids.append(state["knowledge_doc_id"])
        doc_ids += [d for d in GUIDANCE_DOCS if d not in doc_ids]
        seen, unique = set(), []
        for doc in self._assets.documents(doc_ids, scopes=(asset["asset_class"], "ALL")):
            if doc["doc_id"] not in seen:
                seen.add(doc["doc_id"])
                unique.append(doc)
        return unique

    def work_orders(self, identifier: str, limit: int):
        return self._assets.work_orders(self.resolve(identifier)["asset_id"], limit)
