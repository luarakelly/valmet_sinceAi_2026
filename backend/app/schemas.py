"""Pydantic Request & Response Schemas for FastAPI REST APIs.

Provides serialization, response DTOs, and request input validation for:
- Asset listings, details, and composites
- 3D spatial scene anchors with health overlays
- Time-series telemetry slices
- Alarms and maintenance events
- AI Diagnostics Copilot queries with evidence citations
- Draft work orders
- Avatar autonomous navigation routing
- Proximity detection and plant metaverse summary KPIs
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid
from pydantic import BaseModel, Field, ConfigDict


# ==========================================
# 1. Spatial Scene Anchor Schemas
# ==========================================

class SceneAnchorRead(BaseModel):
    """3D anchor position, bounding box, and embedded health state for Three.js rendering."""
    model_config = ConfigDict(from_attributes=True)

    scene_anchor_id: str
    asset_id: str
    tag: str
    area_id: str
    x_local_m: float
    y_local_m: float
    z_local_m: float
    bbox_x_m: float = 1.0
    bbox_y_m: float = 1.0
    bbox_z_m: float = 1.0
    mapping_confidence: float = 0.65
    mapping_status: Optional[str] = None
    scene_path: Optional[str] = None

    # Overlaid health attributes from CurrentState
    health_score: Optional[float] = None
    condition_state: Optional[str] = None
    issue_code: Optional[str] = None


# ==========================================
# 2. Operational State & Knowledge Schemas
# ==========================================

class CurrentStateRead(BaseModel):
    """Operational health condition, diagnostic state, and model confidence."""
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    tag: str
    asset_class: str
    area_name: str
    criticality: str
    health_score: float
    condition_state: str
    issue_code: str
    issue_summary: Optional[str] = None
    urgency: str = "routine"
    recommended_next_check: Optional[str] = None
    model_confidence: float = 0.85
    last_updated: Optional[datetime] = None
    knowledge_doc_id: Optional[str] = None


class KnowledgeDocRead(BaseModel):
    """Authoritative engineering standard or safety guardrail."""
    model_config = ConfigDict(from_attributes=True)

    doc_id: str
    title: str
    scope: str
    content: str


# ==========================================
# 3. Asset Hierarchy & Composite Schemas
# ==========================================

class AssetRead(BaseModel):
    """Asset master record with joined current state and scene anchor."""
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    tag: str
    asset_class: str
    area_id: str
    area_name: str
    process_context: Optional[str] = None
    criticality: str
    installation_date: Optional[datetime] = None
    last_service_date: Optional[datetime] = None
    service_interval_days: Optional[int] = 180
    connectivity_profile: Optional[str] = "OPC_UA"
    scene_anchor_id: Optional[str] = None
    qr_id: Optional[str] = None
    nfc_id: Optional[str] = None

    # Joined components
    current_state: Optional[CurrentStateRead] = None
    state: Optional[CurrentStateRead] = None
    anchor: Optional[SceneAnchorRead] = None


class TelemetryRead(BaseModel):
    """Time-series sensor telemetry reading with sparse metrics."""
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    timestamp: datetime
    asset_id: str
    tag: str
    asset_class: str
    area_id: str
    process_pressure_bar: Optional[float] = None
    process_flow_pct: Optional[float] = None
    position_setpoint_pct: Optional[float] = None
    position_actual_pct: Optional[float] = None
    pneumatic_supply_bar: Optional[float] = None
    stiction_index: Optional[float] = None
    load_for_opening_pct: Optional[float] = None
    vibration_mm_s: Optional[float] = None
    bearing_temp_c: Optional[float] = None
    motor_current_a: Optional[float] = None
    speed_rpm: Optional[float] = None
    signal_quality_pct: Optional[float] = 99.0
    sensor_bias: Optional[float] = None


class AlarmEventRead(BaseModel):
    """Alarm, condition change, or diagnostic alert event."""
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    timestamp: datetime
    asset_id: str
    tag: str
    area_name: str
    event_type: str
    severity: str
    event_code: str
    description: str
    source: str
    status: str


class MaintenanceHistoryRead(BaseModel):
    """Past work order record."""
    model_config = ConfigDict(from_attributes=True)

    work_order_id: str
    asset_id: str
    tag: str
    area_name: str
    opened_at: datetime
    action: str
    maintenance_type: str
    priority: str
    result: str
    duration_h: float = 1.0
    downtime_h: float = 0.0
    role: str = "field_technician"
    knowledge_doc_id: Optional[str] = None


class DataQualityRead(BaseModel):
    """Data quality or sensor anomaly record."""
    model_config = ConfigDict(from_attributes=True)

    issue_id: str
    asset_id: str
    tag: str
    issue_type: str
    severity: str
    source_sheet: str
    recommended_handling: str


class HistoricalServiceCaseRead(BaseModel):
    """Diagnostic reference case record."""
    model_config = ConfigDict(from_attributes=True)

    case_id: str
    asset_class: str
    historical_issue_code: str
    historical_interpretation: str
    recommended_next_check: str
    safe_evidence_workflow: str
    severity: str
    knowledge_doc_id: Optional[str] = None
    fairness_note: Optional[str] = None


class AssetDetailRead(AssetRead):
    """Complete 360-degree composite asset detail view."""
    recent_telemetry: List[TelemetryRead] = []
    recent_events: List[AlarmEventRead] = []
    maintenance_history: List[MaintenanceHistoryRead] = []
    work_orders: List[MaintenanceHistoryRead] = []
    knowledge_docs: List[KnowledgeDocRead] = []
    knowledge_doc: Optional[KnowledgeDocRead] = None
    data_quality_issues: List[DataQualityRead] = []


# ==========================================
# 4. AI Diagnostics Copilot Schemas (R4 / F16 / F17)
# ==========================================

class EvidenceCitation(BaseModel):
    source_type: str = "doc"
    source_id: str
    description: str
    confidence: float = 0.90


class CopilotQueryRequest(BaseModel):
    """Diagnostic query command directed to an asset."""
    asset_id: str = Field(description="Target asset identifier or tag (e.g. ASSET-017 or P-005)")
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
        default="gemini-2.5-flash",
        description="AI generation model or deterministic fallback mode"
    )
    suggested_work_order: Optional[Dict[str, Any]] = None

    # Compatibility aliases
    asset_class: Optional[str] = None
    diagnosis_summary: Optional[str] = None
    multivariate_evidence: List[str] = []
    citations: List[EvidenceCitation] = []
    recommended_action: Optional[str] = None
    safety_guardrails: List[str] = []
    confidence_score: Optional[float] = None
    work_order_draft_ready: bool = True


# ==========================================
# 5. Work Order Draft Schemas (R2 / F06)
# ==========================================

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

    # Compatibility aliases
    area_name: Optional[str] = None
    recommended_role: Optional[str] = None
    estimated_duration_h: Optional[float] = 1.0
    safety_instructions: List[str] = []


# ==========================================
# 6. Autonomous Navigation Schemas (R3 / F11)
# ==========================================

class NavigationRouteRequest(BaseModel):
    """Request pathfinding from avatar start position to an asset."""
    start: List[float] = Field(description="Current avatar 3D position [x, y, z]")
    target_asset_id: str = Field(description="Destination asset ID or tag")


class NavigationRouteResponse(BaseModel):
    """Obstacle-free collision-avoiding trajectory waypoints."""
    target_asset_id: str
    target_tag: str
    total_distance_m: float
    waypoints: List[List[float]] = Field(description="Ordered list of [x, y, z] navigation waypoints")


# ==========================================
# 7. Proximity & Metaverse Dashboard Schemas (R4 / F14 / F19)
# ==========================================

class ProximityQueryRequest(BaseModel):
    """Query nearby assets relative to avatar position."""
    x: float
    y: float
    z: float
    radius_m: float = 3.0


class ProximityAssetResponse(BaseModel):
    """Asset within avatar interaction radius with fault status."""
    asset_id: str
    tag: str
    distance_m: float
    health_score: float
    condition_state: str
    issue_code: str
    is_faulty: bool
    anchor: SceneAnchorRead


class DashboardSummaryResponse(BaseModel):
    """Overall plant metaverse operational health summary."""
    total_assets: int = 30
    average_health_score: float = 81.2
    condition_counts: Dict[str, int] = {}
    healthy_count: int = 17
    watch_count: int = 4
    degraded_count: int = 6
    attention_required_count: int = 3
    total_telemetry_samples: int = 4320
    total_alarms_events: int = 1000
    active_alarms_count: int = 512
    high_severity_events: int = 153
    total_maintenance_records: int = 300
    open_work_orders_count: int = 42
    total_data_quality_issues: int = 120
    data_quality_issues_count: int = 120


MetaverseDashboardResponse = DashboardSummaryResponse


# ==========================================
# Legacy Nutrition Schemas (Backwards Compatibility)
# ==========================================

class UserCreate(BaseModel):
    name: str
    email: str
    password: str


class UserDelete(BaseModel):
    name: str
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    email: str
    created_at: datetime
    updated_at: datetime


class CatalogBase(BaseModel):
    type: str
    name: str
    brand: Optional[str] = None
    calories: float = 0.0
    protein: float = 0.0
    carbs: float = 0.0
    fat: float = 0.0
    contents_json: List[Dict[str, Any]] = []
    meta_json: Dict[str, Any] = {}


class CatalogCreate(CatalogBase):
    pass


class CatalogRead(CatalogBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class JournalBase(BaseModel):
    user_id: uuid.UUID
    catalog_id: Optional[uuid.UUID] = None
    type: str
    timestamp: datetime
    amount: float = 0.0
    unit: Optional[str] = None
    meta_json: Dict[str, Any] = {}


class JournalCreate(JournalBase):
    pass


class JournalRead(JournalBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# Aliases
AssetStateRead = CurrentStateRead
WorkOrderRead = MaintenanceHistoryRead
