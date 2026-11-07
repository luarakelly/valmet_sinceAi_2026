"""Copilot API contracts (/api/copilot/query)."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EvidenceCitation(BaseModel):
    source_type: str = "doc"
    source_id: str
    description: str
    confidence: float = 0.90


class CopilotQueryRequest(BaseModel):
    """Diagnostic query command directed to an asset."""
    asset_id: Optional[str] = Field(
        default=None,
        description="Target asset identifier or tag (e.g. ASSET-017 or P-005)"
    )
    query: Optional[str] = Field(
        default="Diagnose current condition and provide recommended next checks",
        description="Technician question or diagnostic intent"
    )
    prompt: Optional[str] = None  # Compatibility alias for query
    user_role: Optional[str] = Field(default="field_technician", description="Role of requesting user")
    include_telemetry: bool = Field(default=True, description="Include recent telemetry trends in prompt context")
    include_history: bool = Field(default=True, description="Include past work orders in prompt context")
    include_evidence: bool = Field(default=True)


class CopilotQueryResponse(BaseModel):
    """Evidence-grounded diagnostic assessment with citations and safety checks."""
    asset_id: str
    tag: str
    health_score: float
    condition_state: str
    issue_code: Optional[str] = "NORMAL"
    diagnosis: Optional[str] = None
    evidence_citations: List[str] = Field(
        default=[],
        description="Explicit evidence IDs cited (EVT-XXXXX, WO-XXXXX, DOC-XXXXX, Telemetry timestamps)"
    )
    safety_checks: List[str] = Field(
        default=[],
        description="Mandatory field-service safety checks (PPE, LOTO, zero-energy isolation) per DOC-FIELD-SAFETY"
    )
    recommended_actions: List[str] = Field(
        default=[],
        description="Actionable, safe next inspection steps"
    )
    model_confidence: float = Field(default=0.85, description="Calculated AI diagnostic confidence (0.0 to 1.0)")
    grounded_mode: str = Field(
        default="deterministic-evidence-engine",
        description="Engine that produced the answer; LLM answers are accepted only with verified citations"
    )
    answer: Optional[str] = Field(default=None, description="LLM answer to the technician's question, when enabled")
    suggested_work_order: Optional[Dict[str, Any]] = None
    action: Optional[str] = Field(default=None, description="Robot/environment action: navigate, select, diagnose, reset")
    target_asset_id: Optional[str] = Field(default=None, description="Target asset identifier for action")

    asset_class: Optional[str] = None
    diagnosis_summary: Optional[str] = None
    multivariate_evidence: List[str] = []
    citations: List[EvidenceCitation] = []
    recommended_action: Optional[str] = None
    safety_guardrails: List[str] = []
    confidence_score: Optional[float] = None
    work_order_draft_ready: bool = True
