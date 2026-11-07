"""Ask Your Factory SQLModel Database Models.

Defines the 10 core entity models representing the Valmet industrial plant:
1. KnowledgeDoc (knowledge_docs): 8 engineering and safety guidelines
2. AssetMaster / Asset (assets): 30 physical equipment records
3. SceneAnchor (scene_anchors): 30 3D spatial anchor bounding boxes
4. CurrentState (current_states): 30 equipment operational health states
5. TelemetrySample / Telemetry (telemetry_samples): 4,320 multivariate sensor readings
6. AlarmEvent (alarms_events): 1,000 industrial alarms and inspection events
7. MaintenanceHistory (maintenance_history): 300 past work orders
8. HistoricalServiceCase (historical_service_cases): 50 diagnostic reference cases
9. DataQuality (data_quality_issues): 120 sensor and data pipeline anomaly records
10. RAGCorpusIndex (rag_corpus_index): 38 markdown documents linking asset cards
"""

from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship



class KnowledgeDoc(SQLModel, table=True):
    """Authoritative engineering, diagnostic, and safety guidelines."""
    __tablename__ = "knowledge_docs"

    doc_id: str = Field(primary_key=True, index=True, description="Document identifier (e.g. DOC-FIELD-SAFETY)")
    title: str = Field(description="Document title")
    scope: str = Field(index=True, description="Applicable equipment class or ALL")
    content: str = Field(description="Full text markdown of guidelines and requirements")
    synthetic_record: bool = Field(default=True, description="Synthetic data flag")

    service_cases: List["HistoricalServiceCase"] = Relationship(back_populates="knowledge_doc")



class AssetMaster(SQLModel, table=True):
    """Master asset hierarchy containing the 30 industrial equipment units."""
    __tablename__ = "assets"

    asset_id: str = Field(primary_key=True, index=True, description="Canonical asset ID (e.g. ASSET-001)")
    tag: str = Field(unique=True, index=True, description="Engineering tag (e.g. CV-001, P-005, M-001)")
    asset_class: str = Field(index=True, description="Equipment category (CONTROL_VALVE, PROCESS_PUMP, etc.)")
    area_id: str = Field(index=True, description="Plant area identifier (AREA-01 to AREA-05)")
    area_name: str = Field(description="Area name (e.g. Utility Island, Stock Preparation)")
    process_context: Optional[str] = Field(default=None, description="Process context (utilities, chemical, process)")
    criticality: str = Field(default="C - standard", index=True, description="Criticality rating (A - production critical, B, C)")
    installation_date: Optional[datetime] = Field(default=None, description="Equipment installation date")
    last_service_date: Optional[datetime] = Field(default=None, description="Most recent service date")
    service_interval_days: Optional[int] = Field(default=180, description="Scheduled service interval in days")
    connectivity_profile: Optional[str] = Field(default="OPC_UA", description="Field connectivity protocol")
    scene_anchor_id: Optional[str] = Field(default=None, index=True, description="Linked 3D scene anchor ID")
    qr_id: Optional[str] = Field(default=None, description="Synthetic QR badge code")
    nfc_id: Optional[str] = Field(default=None, description="Synthetic NFC badge code")
    data_classification: Optional[str] = Field(default="SYNTHETIC", description="Data governance classification")
    synthetic_record: bool = Field(default=True, description="Synthetic record flag")

    anchor: Optional["SceneAnchor"] = Relationship(back_populates="asset")
    current_state: Optional["CurrentState"] = Relationship(back_populates="asset")
    telemetry: List["TelemetrySample"] = Relationship(back_populates="asset")
    alarms: List["AlarmEvent"] = Relationship(back_populates="asset")
    maintenance_records: List["MaintenanceHistory"] = Relationship(back_populates="asset")
    data_quality_issues: List["DataQuality"] = Relationship(back_populates="asset")



class SceneAnchor(SQLModel, table=True):
    """3D spatial anchor defining local coordinates and bounding box dimensions in the scene."""
    __tablename__ = "scene_anchors"

    scene_anchor_id: str = Field(primary_key=True, index=True, description="Anchor identifier (e.g. ANCHOR-001)")
    asset_id: str = Field(unique=True, index=True, foreign_key="assets.asset_id", description="Linked asset identifier")
    tag: str = Field(index=True, description="Engineering tag")
    area_id: str = Field(description="Plant area identifier")
    x_local_m: float = Field(description="Local X coordinate in meters")
    y_local_m: float = Field(description="Local Y coordinate in meters")
    z_local_m: float = Field(description="Local Z coordinate in meters")
    bbox_x_m: float = Field(default=1.0, description="Bounding box width in meters (X dimension)")
    bbox_y_m: float = Field(default=1.0, description="Bounding box height in meters (Y dimension)")
    bbox_z_m: float = Field(default=1.0, description="Bounding box depth in meters (Z dimension)")
    scene_path: Optional[str] = Field(default=None, description="Virtual scene hierarchy path")
    mapping_status: Optional[str] = Field(default="placeholder_until_valmet_scene_received")
    identity_methods: Optional[str] = Field(default="asset_id / QR / NFC / manual mapping")
    mapping_confidence: float = Field(default=0.65, description="Anchor positioning confidence")
    remap_instruction: Optional[str] = Field(default=None, description="Remapping notes")
    synthetic_record: bool = Field(default=True)

    asset: Optional[AssetMaster] = Relationship(back_populates="anchor")



class CurrentState(SQLModel, table=True):
    """Operational health condition, diagnostic state, and AI model confidence for each asset."""
    __tablename__ = "current_states"

    asset_id: str = Field(primary_key=True, foreign_key="assets.asset_id", description="Asset ID (PK & FK)")
    tag: str = Field(index=True, description="Engineering tag")
    asset_class: str = Field(description="Equipment class")
    area_name: str = Field(description="Plant area name")
    criticality: str = Field(description="Asset criticality")
    health_score: float = Field(index=True, description="Composite health index (0 to 100)")
    condition_state: str = Field(index=True, description="State (healthy, watch, degraded, attention_required)")
    issue_code: str = Field(index=True, description="Primary diagnostic code (NORMAL, FOULING, CAVITATION_RISK, etc.)")
    issue_summary: Optional[str] = Field(default=None, description="Human-readable diagnostic summary")
    urgency: str = Field(default="routine", description="Maintenance urgency (routine, medium, high)")
    recommended_next_check: Optional[str] = Field(default=None, description="Suggested inspection check")
    model_confidence: float = Field(default=0.85, description="Diagnostic model confidence (0.0 to 1.0)")
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="State timestamp")
    knowledge_doc_id: Optional[str] = Field(default=None, foreign_key="knowledge_docs.doc_id", description="Linked reference doc")
    synthetic_record: bool = Field(default=True)

    asset: Optional[AssetMaster] = Relationship(back_populates="current_state")
    knowledge_doc: Optional[KnowledgeDoc] = Relationship()



class TelemetrySample(SQLModel, table=True):
    """Multivariate time-series telemetry samples (30-minute intervals over 3 days)."""
    __tablename__ = "telemetry_samples"

    id: Optional[int] = Field(default=None, primary_key=True, description="Autoincrement primary key")
    timestamp: datetime = Field(index=True, description="Reading timestamp (UTC)")
    asset_id: str = Field(index=True, foreign_key="assets.asset_id", description="Asset identifier")
    tag: str = Field(index=True, description="Engineering tag")
    asset_class: str = Field(description="Equipment category")
    area_id: str = Field(description="Plant area identifier")

    process_pressure_bar: Optional[float] = Field(default=None, description="Process line pressure in bar")
    process_flow_pct: Optional[float] = Field(default=None, description="Process flow rate percentage")
    position_setpoint_pct: Optional[float] = Field(default=None, description="Valve setpoint position (0-100%)")
    position_actual_pct: Optional[float] = Field(default=None, description="Valve measured position (0-100%)")
    pneumatic_supply_bar: Optional[float] = Field(default=None, description="Valve pneumatic air supply in bar")
    stiction_index: Optional[float] = Field(default=None, description="Valve friction/stiction diagnostic index")
    load_for_opening_pct: Optional[float] = Field(default=None, description="Torque/load required to crack open valve")
    vibration_mm_s: Optional[float] = Field(default=None, description="Overall vibration velocity in mm/s RMS")
    bearing_temp_c: Optional[float] = Field(default=None, description="Bearing temperature in degrees Celsius")
    motor_current_a: Optional[float] = Field(default=None, description="Motor electric current in Amperes")
    speed_rpm: Optional[float] = Field(default=None, description="Rotational speed in RPM")
    signal_quality_pct: float = Field(default=99.0, description="Sensor signal quality index (0-100%)")
    sensor_bias: Optional[float] = Field(default=None, description="Estimated sensor calibration bias")
    source_profile: Optional[str] = Field(default="simulated_30min_stream")
    synthetic_record: bool = Field(default=True)

    asset: Optional[AssetMaster] = Relationship(back_populates="telemetry")



class AlarmEvent(SQLModel, table=True):
    """Alarm, condition change, inspection note, or maintenance notification event."""
    __tablename__ = "alarms_events"

    event_id: str = Field(primary_key=True, index=True, description="Event identifier (e.g. EVT-00001)")
    timestamp: datetime = Field(index=True, description="Event trigger timestamp (UTC)")
    asset_id: str = Field(index=True, foreign_key="assets.asset_id", description="Target asset identifier")
    tag: str = Field(index=True, description="Engineering tag")
    area_name: str = Field(description="Plant area name")
    event_type: str = Field(index=True, description="Event category (CONDITION_CHANGE, DIAGNOSTIC_ALERT, etc.)")
    severity: str = Field(index=True, description="Severity level (low, medium, high)")
    event_code: str = Field(index=True, description="Event code (e.g. ALERT_ACTIVE, TREND_UPDATE)")
    description: str = Field(description="Event description text")
    source: str = Field(default="edge_sensor", description="Event source (scada, dcs, edge_sensor, mobile_app)")
    status: str = Field(default="open", description="Event state (open, acknowledged, closed)")
    synthetic_record: bool = Field(default=True)

    asset: Optional[AssetMaster] = Relationship(back_populates="alarms")



class MaintenanceHistory(SQLModel, table=True):
    """Historical maintenance work orders with duration, downtime, outcome, and personnel role."""
    __tablename__ = "maintenance_history"

    work_order_id: str = Field(primary_key=True, index=True, description="Work order code (e.g. WO-00001)")
    asset_id: str = Field(index=True, foreign_key="assets.asset_id", description="Target asset identifier")
    tag: str = Field(index=True, description="Engineering tag")
    area_name: str = Field(description="Plant area name")
    opened_at: datetime = Field(index=True, description="Work order creation timestamp (UTC)")
    action: str = Field(description="Maintenance action taken (e.g. seal inspection, planned valve service)")
    maintenance_type: str = Field(index=True, description="Type (preventive, inspection, corrective, predictive)")
    priority: str = Field(index=True, description="Priority (low, medium, high)")
    result: str = Field(description="Outcome (service_completed, no_fault_found, follow_up_required)")
    duration_h: float = Field(default=1.0, description="Work order duration in hours")
    downtime_h: float = Field(default=0.0, description="Equipment downtime in hours")
    role: str = Field(default="field_technician", description="Technician discipline")
    knowledge_doc_id: Optional[str] = Field(default=None, foreign_key="knowledge_docs.doc_id", description="Linked doc")
    synthetic_record: bool = Field(default=True)

    asset: Optional[AssetMaster] = Relationship(back_populates="maintenance_records")
    knowledge_doc: Optional[KnowledgeDoc] = Relationship()



class HistoricalServiceCase(SQLModel, table=True):
    """Historical diagnostic reference cases for evidence-grounded AI copilot reasoning."""
    __tablename__ = "historical_service_cases"

    case_id: str = Field(primary_key=True, index=True, description="Case identifier (e.g. CASE-001)")
    asset_class: str = Field(index=True, description="Equipment class")
    historical_issue_code: str = Field(index=True, description="Historical diagnostic fault code")
    historical_interpretation: str = Field(description="Symptom interpretation summary")
    recommended_next_check: str = Field(description="Recommended maintenance check procedure")
    safe_evidence_workflow: str = Field(description="Safe evidence verification workflow")
    severity: str = Field(description="Historical severity rating")
    knowledge_doc_id: Optional[str] = Field(default=None, foreign_key="knowledge_docs.doc_id", description="Linked doc")
    fairness_note: Optional[str] = Field(default=None, description="Synthetic case benchmark disclaimer")
    synthetic_record: bool = Field(default=True)

    knowledge_doc: Optional[KnowledgeDoc] = Relationship(back_populates="service_cases")



class DataQuality(SQLModel, table=True):
    """Synthetic data quality anomalies injected to verify trustworthy copilot degradation."""
    __tablename__ = "data_quality_issues"

    issue_id: str = Field(primary_key=True, index=True, description="Issue code (e.g. DQ-0001)")
    asset_id: str = Field(index=True, foreign_key="assets.asset_id", description="Affected asset identifier")
    tag: str = Field(index=True, description="Engineering tag")
    issue_type: str = Field(index=True, description="Category (timestamp_jitter, sensor_quality_drop, etc.)")
    severity: str = Field(index=True, description="Severity (low, medium, high)")
    source_sheet: str = Field(description="Source table where anomaly manifests")
    recommended_handling: str = Field(description="Recommended mitigation (flag_for_review, reduce_model_confidence)")
    synthetic_record: bool = Field(default=True)

    asset: Optional[AssetMaster] = Relationship(back_populates="data_quality_issues")



class RAGCorpusIndex(SQLModel, table=True):
    """Metadata catalog indexing markdown asset cards and engineering knowledge documents."""
    __tablename__ = "rag_corpus_index"

    doc_id: str = Field(primary_key=True, index=True, description="Document ID (e.g. DOC-ASSET-001)")
    asset_id: Optional[str] = Field(default=None, index=True, description="Linked asset ID or None for general docs")
    tag: Optional[str] = Field(default=None, description="Linked tag or None for general docs")
    scope: str = Field(description="Document scope (equipment class or ALL)")
    file_name: str = Field(description="Physical file name in data pack")
    mime_type: str = Field(default="text/markdown")
    document_role: str = Field(default="asset_card", description="Role (asset_card, reference_doc)")
    synthetic_record: bool = Field(default=True)
