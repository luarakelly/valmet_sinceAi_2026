"""Asset API contracts: master data, current state, anchors and evidence records."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


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

    health_score: Optional[float] = None
    condition_state: Optional[str] = None
    issue_code: Optional[str] = None


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
