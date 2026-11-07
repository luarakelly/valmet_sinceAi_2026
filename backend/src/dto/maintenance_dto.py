"""Maintenance prioritisation contract (/api/maintenance/priorities)."""

from typing import List, Optional

from pydantic import BaseModel


class MaintenancePriorityRead(BaseModel):
    rank: int
    asset_id: str
    tag: str
    asset_class: str
    health_score: float
    condition_state: str
    issue_code: Optional[str] = None
    issue_summary: Optional[str] = None
    urgency: Optional[str] = None
    criticality: str
    score: float
    reasons: List[str]
    scene_object_id: Optional[str] = None
