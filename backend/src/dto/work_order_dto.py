"""Draft work order contracts (draft only; never a control action)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class WorkOrderDraftRequest(BaseModel):
    """Draft work order submission (human review only; no live field actuation)."""
    asset_id: str
    action: Optional[str] = None
    maintenance_type: str = "corrective"
    priority: str = "medium"
    role: str = "field_technician"
    description: Optional[str] = None
    notes: Optional[str] = None
    safety_acknowledged: bool = True


class WorkOrderDraftResponse(BaseModel):
    """Confirmation of recorded draft work order."""
    work_order_id: str
    asset_id: str
    tag: str
    status: str = "draft"
    created_at: datetime
    action: str
    maintenance_type: str
    priority: str
    role: str = "field_technician"
    safety_checklist: List[str] = []

    area_name: Optional[str] = None
    recommended_role: Optional[str] = None
    estimated_duration_h: Optional[float] = 1.0
    safety_instructions: List[str] = []
