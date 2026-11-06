"""Ask Your Factory REST API Router.

Implements official API Contract from valmet_builder_pack.xlsx & PROJECT.md:
- GET  /api/assets              (List 30 assets with area, tag, criticality, condition_state, health_score, anchor)
- GET  /api/assets/{id}         (Single asset detail joined with current_state, anchor, docs, data quality)
- GET  /api/assets/{id}/telemetry (Time-series telemetry samples, optional query params limit, start_time, end_time)
- GET  /api/assets/{id}/events    (Alarms and events, optional query params limit, severity, event_type, status)
- GET  /api/assets/{id}/documents (Linked operating and safety guidelines from Knowledge_Docs & RAG index)
- GET  /api/scene/anchors       (All 30 spatial anchors with coordinates x, y, z, dimensions, health score)
- POST /api/work-orders/draft   (Create draft work order in Maintenance_History with DOC-FIELD-SAFETY guardrails)
- GET  /api/metaverse/dashboard (Aggregate plant KPIs from Dashboard sheet)
- POST /api/scene/proximity     (Euclidean distance query for avatar proximity detection)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.database import get_session
from app.models import (
    AssetMaster as Asset,
    SceneAnchor,
    CurrentState,
    TelemetrySample as Telemetry,
    AlarmEvent,
    MaintenanceHistory,
    KnowledgeDoc,
    DataQuality,
    RAGCorpusIndex,
)

from app.schemas import (
    AssetRead,
    AssetDetailRead,
    CurrentStateRead,
    SceneAnchorRead,
    TelemetryRead,
    AlarmEventRead,
    MaintenanceHistoryRead,
    KnowledgeDocRead,
    DataQualityRead,
    WorkOrderDraftRequest,
    WorkOrderDraftResponse,
    ProximityQueryRequest,
    ProximityAssetResponse,
    DashboardSummaryResponse,
    MetaverseDashboardResponse,
)

router = APIRouter(tags=["Ask Your Factory"])



def get_asset_or_404(session: Session, identifier: str) -> Asset:
    """Resolve an asset by asset_id (e.g. ASSET-017) or tag (e.g. P-005), case-insensitively.
    
    Raises HTTP 404 if the identifier does not match any registered asset.
    """
    clean_id = identifier.strip()
    stmt = select(Asset).where(
        (Asset.asset_id == clean_id)
        | (func.lower(Asset.asset_id) == clean_id.lower())
        | (Asset.tag == clean_id)
        | (func.lower(Asset.tag) == clean_id.lower())
    )
    asset = session.exec(stmt).first()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset with identifier '{identifier}' not found in asset registry.",
        )
    return asset


def transform_anchor_to_scene(
    x: float, y: float, z: float,
    bx: float, by: float, bz: float
) -> Dict[str, float]:
    """Affine transform mapping Excel [-0.32..30.39m, -0.39..15.49m, 0.47..2.15m] coordinates into
    the Three.js boiler room point cloud envelope [-4.5..4.5m, -1.5..0.0m, -4.5..0.5m].
    
    Mapping:
    - Excel X -> Three.js X
    - Excel Y -> Three.js Z (depth)
    - Excel Z -> Three.js Y (elevation / height)
    """
    x_min, x_max = -0.32, 30.39
    y_min, y_max = -0.39, 15.49
    z_min, z_max = 0.47, 2.15

    if x_max > x_min:
        u = (x - x_min) / (x_max - x_min)
    else:
        u = 0.5

    if y_max > y_min:
        v = (y - y_min) / (y_max - y_min)
    else:
        v = 0.5

    if z_max > z_min:
        w = (z - z_min) / (z_max - z_min)
    else:
        w = 0.5

    x_3d = -4.5 + 9.0 * u
    y_3d = -1.5 + 1.5 * w
    z_3d = -4.5 + 5.0 * v

    return {
        "x_local_m": round(x_3d, 3),
        "y_local_m": round(y_3d, 3),
        "z_local_m": round(z_3d, 3),
        "bbox_x_m": round(bx, 2),
        "bbox_y_m": round(bz, 2),
        "bbox_z_m": round(by, 2),
    }



@router.get("/assets", response_model=List[AssetRead])
def list_assets(
    area_id: Optional[str] = Query(None, description="Filter by area code (e.g. AREA-01 to AREA-05)"),
    asset_class: Optional[str] = Query(None, description="Filter by class (CONTROL_VALVE, PROCESS_PUMP, ELECTRIC_MOTOR, etc.)"),
    criticality: Optional[str] = Query(None, description="Filter by criticality (A - production critical, B, C)"),
    condition_state: Optional[str] = Query(None, description="Filter by condition (healthy, watch, degraded, attention_required)"),
    search: Optional[str] = Query(None, description="Search keyword matching tag, area_name, or asset_id"),
    session: Session = Depends(get_session),
):
    """List assets with embedded current health state and 3D spatial anchor coordinates."""
    stmt = select(Asset)

    if area_id:
        stmt = stmt.where(Asset.area_id == area_id.strip())
    if asset_class:
        stmt = stmt.where(func.lower(Asset.asset_class) == asset_class.strip().lower())
    if criticality:
        stmt = stmt.where(func.lower(Asset.criticality).like(f"%{criticality.strip().lower()}%"))
    if search:
        kw = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            func.lower(Asset.tag).like(kw)
            | func.lower(Asset.area_name).like(kw)
            | func.lower(Asset.asset_id).like(kw)
        )

    assets = session.exec(stmt.order_by(Asset.asset_id.asc())).all()

    asset_ids = [a.asset_id for a in assets]
    state_map: Dict[str, CurrentState] = {}
    anchor_map: Dict[str, SceneAnchor] = {}

    if asset_ids:
        states = session.exec(select(CurrentState).where(CurrentState.asset_id.in_(asset_ids))).all()
        state_map = {s.asset_id: s for s in states}

        anchors = session.exec(select(SceneAnchor).where(SceneAnchor.asset_id.in_(asset_ids))).all()
        anchor_map = {a.asset_id: a for a in anchors}

    results: List[AssetRead] = []
    for a in assets:
        state_obj = state_map.get(a.asset_id)
        anchor_obj = anchor_map.get(a.asset_id)

        if condition_state and state_obj:
            if state_obj.condition_state.lower() != condition_state.strip().lower():
                continue

        if state_obj:
            c_read = CurrentStateRead.model_validate(state_obj)
        else:
            c_read = None

        if anchor_obj:
            a_read = SceneAnchorRead.model_validate(anchor_obj)
        else:
            a_read = None

        if a_read and state_obj:
            a_read.health_score = state_obj.health_score
            a_read.condition_state = state_obj.condition_state
            a_read.issue_code = state_obj.issue_code

        item = AssetRead(
            asset_id=a.asset_id,
            tag=a.tag,
            asset_class=a.asset_class,
            area_id=a.area_id,
            area_name=a.area_name,
            process_context=a.process_context,
            criticality=a.criticality,
            installation_date=a.installation_date,
            last_service_date=a.last_service_date,
            service_interval_days=a.service_interval_days,
            connectivity_profile=a.connectivity_profile,
            scene_anchor_id=a.scene_anchor_id,
            qr_id=a.qr_id,
            nfc_id=a.nfc_id,
            current_state=c_read,
            state=c_read,
            anchor=a_read,
        )
        results.append(item)

    return results


@router.get("/assets/{id}", response_model=AssetDetailRead)
def get_asset_detail(
    id: str,
    session: Session = Depends(get_session),
):
    """Retrieve full 360-degree asset details by asset_id (e.g. ASSET-017) or tag (e.g. P-005)."""
    asset = get_asset_or_404(session, id)

    state = session.exec(select(CurrentState).where(CurrentState.asset_id == asset.asset_id)).first()
    anchor = session.exec(select(SceneAnchor).where(SceneAnchor.asset_id == asset.asset_id)).first()

    doc_cond = (KnowledgeDoc.scope == asset.asset_class) | (KnowledgeDoc.scope == "ALL")
    if state and state.knowledge_doc_id:
        doc_cond = doc_cond | (KnowledgeDoc.doc_id == state.knowledge_doc_id)
    docs = session.exec(select(KnowledgeDoc).where(doc_cond)).all()
    k_reads = [KnowledgeDocRead.model_validate(d) for d in docs]

    dq_issues = session.exec(
        select(DataQuality).where(DataQuality.asset_id == asset.asset_id)
    ).all()
    dq_reads = [DataQualityRead.model_validate(q) for q in dq_issues]

    telemetry_samples = session.exec(
        select(Telemetry)
        .where(Telemetry.asset_id == asset.asset_id)
        .order_by(Telemetry.timestamp.desc())
        .limit(10)
    ).all()
    t_reads = [TelemetryRead.model_validate(s) for s in reversed(telemetry_samples)]

    events = session.exec(
        select(AlarmEvent)
        .where(AlarmEvent.asset_id == asset.asset_id)
        .order_by(AlarmEvent.timestamp.desc())
        .limit(10)
    ).all()
    e_reads = [AlarmEventRead.model_validate(e) for e in events]

    wos = session.exec(
        select(MaintenanceHistory)
        .where(MaintenanceHistory.asset_id == asset.asset_id)
        .order_by(MaintenanceHistory.opened_at.desc())
        .limit(5)
    ).all()
    m_reads = [MaintenanceHistoryRead.model_validate(w) for w in wos]

    if state:
        c_read = CurrentStateRead.model_validate(state)
    else:
        c_read = None

    if anchor:
        a_read = SceneAnchorRead.model_validate(anchor)
    else:
        a_read = None

    if a_read and state:
        a_read.health_score = state.health_score
        a_read.condition_state = state.condition_state
        a_read.issue_code = state.issue_code

    if k_reads:
        primary_doc = k_reads[0]
    else:
        primary_doc = None

    return AssetDetailRead(
        asset_id=asset.asset_id,
        tag=asset.tag,
        asset_class=asset.asset_class,
        area_id=asset.area_id,
        area_name=asset.area_name,
        process_context=asset.process_context,
        criticality=asset.criticality,
        installation_date=asset.installation_date,
        last_service_date=asset.last_service_date,
        service_interval_days=asset.service_interval_days,
        connectivity_profile=asset.connectivity_profile,
        scene_anchor_id=asset.scene_anchor_id,
        qr_id=asset.qr_id,
        nfc_id=asset.nfc_id,
        current_state=c_read,
        state=c_read,
        anchor=a_read,
        recent_telemetry=t_reads,
        recent_events=e_reads,
        maintenance_history=m_reads,
        work_orders=m_reads,
        knowledge_docs=k_reads,
        knowledge_doc=primary_doc,
        data_quality_issues=dq_reads,
    )


@router.get("/assets/{id}/telemetry", response_model=List[TelemetryRead])
def get_asset_telemetry(
    id: str,
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum samples to return"),
    start_time: Optional[datetime] = Query(None, description="Filter samples on or after ISO timestamp"),
    end_time: Optional[datetime] = Query(None, description="Filter samples on or before ISO timestamp"),
    session: Session = Depends(get_session),
):
    """Retrieve time-series telemetry samples for an asset, ordered chronologically ascending."""
    asset = get_asset_or_404(session, id)

    stmt = select(Telemetry).where(Telemetry.asset_id == asset.asset_id)
    if start_time:
        stmt = stmt.where(Telemetry.timestamp >= start_time)
    if end_time:
        stmt = stmt.where(Telemetry.timestamp <= end_time)

    samples = session.exec(stmt.order_by(Telemetry.timestamp.asc()).limit(limit)).all()
    return [TelemetryRead.model_validate(s) for s in samples]


@router.get("/assets/{id}/events", response_model=List[AlarmEventRead])
def get_asset_events(
    id: str,
    limit: int = Query(default=50, ge=1, le=500, description="Maximum events to return"),
    severity: Optional[str] = Query(None, description="Filter by severity: low, medium, high"),
    event_type: Optional[str] = Query(None, description="Filter by event type (e.g. CONDITION_CHANGE, DIAGNOSTIC_ALERT)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (open, acknowledged, closed)"),
    session: Session = Depends(get_session),
):
    """Retrieve recent alarms and events for an asset, ordered newest first."""
    asset = get_asset_or_404(session, id)

    stmt = select(AlarmEvent).where(AlarmEvent.asset_id == asset.asset_id)
    if severity:
        stmt = stmt.where(func.lower(AlarmEvent.severity) == severity.strip().lower())
    if event_type:
        stmt = stmt.where(func.lower(AlarmEvent.event_type) == event_type.strip().lower())
    if status_filter:
        stmt = stmt.where(func.lower(AlarmEvent.status) == status_filter.strip().lower())

    events = session.exec(stmt.order_by(AlarmEvent.timestamp.desc()).limit(limit)).all()
    return [AlarmEventRead.model_validate(e) for e in events]


@router.get("/assets/{id}/documents", response_model=List[KnowledgeDocRead])
def get_asset_documents(
    id: str,
    session: Session = Depends(get_session),
):
    """Retrieve RAG-ready engineering docs and safety guardrails applicable to an asset."""
    asset = get_asset_or_404(session, id)

    state = session.exec(select(CurrentState).where(CurrentState.asset_id == asset.asset_id)).first()
    doc_ids = []
    if state and state.knowledge_doc_id:
        doc_ids.append(state.knowledge_doc_id)

    mandatory_docs = ["DOC-FIELD-SAFETY", "DOC-RAG-GUIDE", "DOC-3D-MAPPING"]
    for m in mandatory_docs:
        if m not in doc_ids:
            doc_ids.append(m)

    docs = session.exec(
        select(KnowledgeDoc).where(
            (KnowledgeDoc.doc_id.in_(doc_ids))
            | (KnowledgeDoc.scope == asset.asset_class)
            | (KnowledgeDoc.scope == "ALL")
        )
    ).all()

    seen = set()
    unique_docs: List[KnowledgeDocRead] = []
    for d in docs:
        if d.doc_id not in seen:
            seen.add(d.doc_id)
            unique_docs.append(KnowledgeDocRead.model_validate(d))

    return unique_docs


@router.get("/scene/anchors", response_model=List[SceneAnchorRead])
def get_scene_anchors(
    normalized: bool = Query(
        default=False,
        description="If True, maps raw Excel coordinates into Three.js boiler room envelope [-4.5..4.5m, -1.5..0.0m, -4.5..0.5m]"
    ),
    session: Session = Depends(get_session),
):
    """Return all 30 3D spatial anchors with bounding box dimensions and live health state."""
    anchors = session.exec(select(SceneAnchor).order_by(SceneAnchor.scene_anchor_id.asc())).all()
    states = session.exec(select(CurrentState)).all()
    state_map = {s.asset_id: s for s in states}

    results: List[SceneAnchorRead] = []
    for a in anchors:
        st = state_map.get(a.asset_id)
        
        if st:
            health_score_val = st.health_score
            condition_state_val = st.condition_state
            issue_code_val = st.issue_code
        else:
            health_score_val = 100.0
            condition_state_val = "healthy"
            issue_code_val = "NORMAL"

        if normalized:
            coords = transform_anchor_to_scene(
                a.x_local_m, a.y_local_m, a.z_local_m,
                a.bbox_x_m, a.bbox_y_m, a.bbox_z_m
            )
            item = SceneAnchorRead(
                scene_anchor_id=a.scene_anchor_id,
                asset_id=a.asset_id,
                tag=a.tag,
                area_id=a.area_id,
                x_local_m=coords["x_local_m"],
                y_local_m=coords["y_local_m"],
                z_local_m=coords["z_local_m"],
                bbox_x_m=coords["bbox_x_m"],
                bbox_y_m=coords["bbox_y_m"],
                bbox_z_m=coords["bbox_z_m"],
                mapping_status=a.mapping_status,
                mapping_confidence=a.mapping_confidence,
                health_score=health_score_val,
                condition_state=condition_state_val,
                issue_code=issue_code_val,
            )
        else:
            item = SceneAnchorRead(
                scene_anchor_id=a.scene_anchor_id,
                asset_id=a.asset_id,
                tag=a.tag,
                area_id=a.area_id,
                x_local_m=a.x_local_m,
                y_local_m=a.y_local_m,
                z_local_m=a.z_local_m,
                bbox_x_m=a.bbox_x_m,
                bbox_y_m=a.bbox_y_m,
                bbox_z_m=a.bbox_z_m,
                mapping_status=a.mapping_status,
                mapping_confidence=a.mapping_confidence,
                health_score=health_score_val,
                condition_state=condition_state_val,
                issue_code=issue_code_val,
            )
        results.append(item)

    return results


@router.post("/work-orders/draft", response_model=WorkOrderDraftResponse, status_code=status.HTTP_201_CREATED)
def create_draft_work_order(
    payload: WorkOrderDraftRequest,
    session: Session = Depends(get_session),
):
    """Create a maintenance draft work order grounded in safety guidelines from DOC-FIELD-SAFETY.
    
    Validates asset identity and safety acknowledgement. Does NOT execute real control actions.
    """
    asset = get_asset_or_404(session, payload.asset_id)

    if not payload.safety_acknowledged:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mandatory safety verification required: You must acknowledge DOC-FIELD-SAFETY guidelines before drafting work orders.",
        )

    stamp = int(datetime.now(timezone.utc).timestamp()) % 100000
    draft_id = f"WO-DRAFT-{stamp:05d}"

    state = session.exec(select(CurrentState).where(CurrentState.asset_id == asset.asset_id)).first()
    if state:
        doc_id = state.knowledge_doc_id
        fallback_action = state.recommended_next_check
    else:
        doc_id = None
        fallback_action = "Inspect and verify equipment condition"

    user_action = (payload.action or "").strip()
    if user_action:
        action_text = user_action
    else:
        action_text = fallback_action

    wo = MaintenanceHistory(
        work_order_id=draft_id,
        asset_id=asset.asset_id,
        tag=asset.tag,
        area_name=asset.area_name,
        opened_at=datetime.now(timezone.utc),
        action=action_text,
        maintenance_type=payload.maintenance_type,
        priority=payload.priority,
        result="draft_created",
        duration_h=1.0,
        downtime_h=0.0,
        role=payload.role,
        knowledge_doc_id=doc_id,
        synthetic_record=True,
    )
    session.add(wo)
    session.commit()
    session.refresh(wo)

    checklist = [
        f"PPE Required: Standard personal protective equipment for {asset.area_name} (Hard Hat, Eye Protection, Safety Boots).",
        f"Lockout/Tagout (LOTO): Perform electrical and mechanical power isolation on {asset.tag} before touching casing or wiring.",
        f"Depressurization Check: Verify process pressure is at 0 bar gauge and cool down below 40°C.",
        f"Field Permit: Confirm active Work-at-Height or Hot-Work permits if applicable.",
    ]

    return WorkOrderDraftResponse(
        work_order_id=draft_id,
        asset_id=asset.asset_id,
        tag=asset.tag,
        status="draft",
        created_at=wo.opened_at,
        action=wo.action,
        maintenance_type=wo.maintenance_type,
        priority=wo.priority,
        role=wo.role,
        area_name=asset.area_name,
        recommended_role=wo.role,
        estimated_duration_h=wo.duration_h,
        safety_checklist=checklist,
        safety_instructions=checklist,
    )



@router.get("/metaverse/dashboard", response_model=MetaverseDashboardResponse)
def get_metaverse_dashboard(session: Session = Depends(get_session)):
    """Aggregate plant-wide health, operational condition counts, and data quality metrics."""
    total_assets = session.scalar(select(func.count(Asset.asset_id))) or 0
    states = session.exec(select(CurrentState)).all()

    if states:
        avg_health = sum(s.health_score for s in states) / len(states)
    else:
        avg_health = 0.0

    condition_counts = {"healthy": 0, "watch": 0, "degraded": 0, "attention_required": 0}
    for s in states:
        k = s.condition_state.lower()
        condition_counts[k] = condition_counts.get(k, 0) + 1

    total_telemetry = session.scalar(select(func.count(Telemetry.id))) or 0
    total_events = session.scalar(select(func.count(AlarmEvent.event_id))) or 0
    high_events = session.scalar(
        select(func.count(AlarmEvent.event_id)).where(AlarmEvent.severity == "high")
    ) or 0
    total_wos = session.scalar(select(func.count(MaintenanceHistory.work_order_id))) or 0
    total_dq = session.scalar(select(func.count(DataQuality.issue_id))) or 0

    return MetaverseDashboardResponse(
        total_assets=total_assets,
        average_health_score=round(avg_health, 1),
        condition_counts=condition_counts,
        healthy_count=condition_counts.get("healthy", 0),
        watch_count=condition_counts.get("watch", 0),
        degraded_count=condition_counts.get("degraded", 0),
        attention_required_count=condition_counts.get("attention_required", 0),
        total_telemetry_samples=total_telemetry,
        total_alarms_events=total_events,
        high_severity_events=high_events,
        total_maintenance_records=total_wos,
        total_data_quality_issues=total_dq,
    )


@router.post("/scene/proximity", response_model=List[ProximityAssetResponse])
def query_proximity(
    payload: ProximityQueryRequest,
    session: Session = Depends(get_session),
):
    """Calculate Euclidean distance from avatar position (x, y, z) to all asset anchors.
    
    Returns assets within radius_m, flagging faulty equipment (health < 70) for dynamic highlights.
    """
    anchors = session.exec(select(SceneAnchor)).all()
    states = session.exec(select(CurrentState)).all()
    state_map = {s.asset_id: s for s in states}

    nearby: List[ProximityAssetResponse] = []
    px, py, pz = payload.x, payload.y, payload.z
    r = payload.radius_m

    for a in anchors:
        dx = a.x_local_m - px
        dy = a.y_local_m - py
        dz = a.z_local_m - pz
        dist = (dx * dx + dy * dy + dz * dz) ** 0.5

        if dist <= r:
            st = state_map.get(a.asset_id)
            if st:
                health = st.health_score
                cond = st.condition_state
                issue = st.issue_code
            else:
                health = 100.0
                cond = "healthy"
                issue = "NORMAL"
            is_faulty = (health < 70.0) or (cond in ("attention_required", "degraded"))

            a_read = SceneAnchorRead.model_validate(a)
            a_read.health_score = health
            a_read.condition_state = cond
            a_read.issue_code = issue

            nearby.append(
                ProximityAssetResponse(
                    asset_id=a.asset_id,
                    tag=a.tag,
                    distance_m=round(dist, 2),
                    health_score=health,
                    condition_state=cond,
                    issue_code=issue,
                    is_faulty=is_faulty,
                    anchor=a_read,
                )
            )

    nearby.sort(key=lambda item: item.distance_m)
    return nearby
