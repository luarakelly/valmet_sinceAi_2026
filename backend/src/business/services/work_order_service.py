"""Draft work orders: recorded for human review; never a control action."""

from datetime import datetime, timezone
from typing import Any, Dict

from business.errors import InvalidRequestError
from business.interfaces.ports.outbound import AssetRepository
from business.services.asset_service import AssetService


class WorkOrderService:
    def __init__(self, assets: AssetRepository, catalog: AssetService):
        self._assets = assets
        self._catalog = catalog

    def draft(self, request: Dict[str, Any]) -> Dict[str, Any]:
        asset = self._catalog.resolve(request["asset_id"])
        if not request.get("safety_acknowledged", True):
            raise InvalidRequestError(
                "Mandatory safety verification required: You must acknowledge DOC-FIELD-SAFETY "
                "guidelines before drafting work orders."
            )
        now = datetime.now(timezone.utc)
        draft_id = "WO-DRAFT-{:05d}".format(int(now.timestamp()) % 100000)
        state = self._assets.states([asset["asset_id"]]).get(asset["asset_id"])
        doc_id = state.get("knowledge_doc_id") if state else None
        fallback = state.get("recommended_next_check") if state else "Inspect and verify equipment condition"
        action = (request.get("action") or "").strip() or fallback

        record = self._assets.add_work_order({
            "work_order_id": draft_id,
            "asset_id": asset["asset_id"],
            "tag": asset["tag"],
            "area_name": asset["area_name"],
            "opened_at": now,
            "action": action,
            "maintenance_type": request.get("maintenance_type", "corrective"),
            "priority": request.get("priority", "medium"),
            "result": "draft_created",
            "duration_h": 1.0,
            "downtime_h": 0.0,
            "role": request.get("role", "field_technician"),
            "knowledge_doc_id": doc_id,
            "synthetic_record": True,
        })
        checklist = [
            "PPE Required: Standard personal protective equipment for {} (Hard Hat, Eye Protection, Safety Boots).".format(asset["area_name"]),
            "Lockout/Tagout (LOTO): Perform electrical and mechanical power isolation on {} before touching casing or wiring.".format(asset["tag"]),
            "Depressurization Check: Verify process pressure is at 0 bar gauge and cool down below 40°C.",
            "Field Permit: Confirm active Work-at-Height or Hot-Work permits if applicable.",
        ]
        return {
            "work_order_id": draft_id,
            "asset_id": asset["asset_id"],
            "tag": asset["tag"],
            "status": "draft",
            "created_at": record["opened_at"],
            "action": record["action"],
            "maintenance_type": record["maintenance_type"],
            "priority": record["priority"],
            "role": record["role"],
            "area_name": asset["area_name"],
            "recommended_role": record["role"],
            "estimated_duration_h": record["duration_h"],
            "safety_checklist": checklist,
            "safety_instructions": checklist,
        }
