"""REST API (mounted at /api), following the builder pack's API_Contract plus scene endpoints.

Assets & evidence: /assets, /assets/{id}, /assets/{id}/telemetry|events|documents|work-orders
Scene:             /scene/frames, /scene/summary, /scene/anchors, /scene/proximity,
                   /scene/extract-assets, /scene/boiler-room.ply, /navigation/path
AI & workflow:     /copilot/query, /work-orders/draft (draft only, never a control action),
                   /vision/analyze, /metaverse/dashboard
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlmodel import Session, select

from app.database import get_session
from app import crud
from app.models import (
    AssetMaster as Asset,
    CurrentState,
    TelemetrySample as Telemetry,
    AlarmEvent,
    MaintenanceHistory,
    KnowledgeDoc,
    DataQuality,
    HistoricalServiceCase,
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
    CopilotQueryRequest,
    CopilotQueryResponse,
)
from app.metaverse.copilot import get_copilot
from app.metaverse.scene_processor import RouteNotFound, get_scene, reset_scene
from app.metaverse.vision import analyze_image

router = APIRouter(tags=["Ask Your Factory"])

FAULTY_STATES = ("degraded", "attention_required")
COPILOT_GUIDANCE_DOCS = ("DOC-FIELD-SAFETY", "DOC-RAG-GUIDE", "DOC-3D-MAPPING")
COPILOT_TELEMETRY_WINDOW = 144  # 3 days at 30-minute resolution



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


def scene_anchor(asset_id: str, state: Optional[CurrentState] = None) -> Optional[SceneAnchorRead]:
    """Anchor of the extracted scene object this asset is bound to (replaces Excel placeholders)."""
    frame = get_scene().find_frame(asset_id)
    if frame is None or frame.get("asset_id") != asset_id:
        return None
    x, y, z = frame["pos"]
    width, height, depth = frame["size"]
    anchor = SceneAnchorRead(
        scene_anchor_id=frame["scene_id"],
        asset_id=asset_id,
        tag=frame["tag"],
        area_id=frame["mapped_asset"]["area_id"],
        x_local_m=x,
        y_local_m=y,
        z_local_m=z,
        bbox_x_m=width,
        bbox_y_m=height,
        bbox_z_m=depth,
        mapping_confidence=frame["mapping_confidence"],
        mapping_status=f"bound_to_extracted_{frame['label'].lower()}",
        scene_path=f"/BoilerRoom/{frame['scene_id']}",
    )
    if state:
        anchor.health_score = state.health_score
        anchor.condition_state = state.condition_state
        anchor.issue_code = state.issue_code
    return anchor


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
    if asset_ids:
        states = session.exec(select(CurrentState).where(CurrentState.asset_id.in_(asset_ids))).all()
        state_map = {s.asset_id: s for s in states}

    results: List[AssetRead] = []
    for a in assets:
        state_obj = state_map.get(a.asset_id)

        if condition_state and state_obj:
            if state_obj.condition_state.lower() != condition_state.strip().lower():
                continue

        if state_obj:
            c_read = CurrentStateRead.model_validate(state_obj)
        else:
            c_read = None
        a_read = scene_anchor(a.asset_id, state_obj)

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

    a_read = scene_anchor(asset.asset_id, state)

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
def get_scene_anchors(session: Session = Depends(get_session)):
    """Anchors of all assets bound to extracted scene objects, with live health state."""
    state_map = {s.asset_id: s for s in session.exec(select(CurrentState)).all()}
    anchors = []
    for frame in get_scene().get_semantic_frames():
        if frame["asset_id"]:
            anchors.append(scene_anchor(frame["asset_id"], state_map.get(frame["asset_id"])))
    return sorted(anchors, key=lambda a: a.asset_id)


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



@router.get("/metaverse/dashboard", response_model=DashboardSummaryResponse)
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

    return DashboardSummaryResponse(
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
    """Assets whose scene object lies within radius_m of the avatar on the floor plane, nearest first."""
    state_map = {s.asset_id: s for s in session.exec(select(CurrentState)).all()}
    nearby: List[ProximityAssetResponse] = []
    for frame in get_scene().nearby(payload.x, payload.z, payload.radius_m):
        state = state_map.get(frame["asset_id"])
        if state is None:
            continue
        nearby.append(
            ProximityAssetResponse(
                asset_id=frame["asset_id"],
                tag=frame["tag"],
                distance_m=frame["distance_m"],
                health_score=state.health_score,
                condition_state=state.condition_state,
                issue_code=state.issue_code,
                is_faulty=state.condition_state in FAULTY_STATES,
                anchor=scene_anchor(frame["asset_id"], state),
            )
        )
    return nearby


@router.get("/assets/{id}/work-orders", response_model=List[MaintenanceHistoryRead])
def get_asset_work_orders(
    id: str,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    """Retrieve maintenance history and service records for an asset."""
    asset = get_asset_or_404(session, id)
    wos = crud.get_asset_work_orders(session, asset.asset_id, limit=limit)
    return [MaintenanceHistoryRead.model_validate(w) for w in wos]


@router.get("/scene/frames")
def get_scene_frames():
    """Every extracted object as a 3D frame (centre + size); bound assets carry their metadata."""
    return get_scene().get_semantic_frames()


@router.get("/scene/summary")
def get_scene_summary():
    """Extraction statistics: algorithm, point count, objects per label, room, entry and target."""
    return get_scene().summary()


@router.post("/scene/extract-assets")
def extract_scene_assets():
    """Re-run the extraction pipeline on the boiler-room point cloud and return all frames."""
    scene = reset_scene()
    return {**scene.summary(), "all_frames": scene.get_semantic_frames()}


@router.get("/navigation/path")
def get_navigation_path(
    target_id: Optional[str] = Query(None, description="Asset ID, tag or object ID; defaults to the faulty target"),
    start_x: Optional[float] = Query(None),
    start_z: Optional[float] = Query(None),
):
    """Collision-free route from the entry (or start_x/start_z) to a standing spot beside the target."""
    start = None
    if start_x is not None and start_z is not None:
        start = (start_x, start_z)
    try:
        return get_scene().get_navigation_path(target_id=target_id, start=start)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No scene object matches '{target_id}'.")
    except RouteNotFound:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"No collision-free route to '{target_id}'.")


@router.get("/scene/boiler-room.ply")
def get_boiler_room_ply():
    """Canonical (Y-up, floor at 0) point cloud for the Three.js PLYLoader."""
    path = get_scene().get_ply_path()
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Boiler room PLY not found on server")
    return FileResponse(path=str(path), media_type="application/octet-stream", filename=path.name)


@router.get("/scene/boiler-room-mesh.ply")
def get_boiler_room_mesh():
    """Surface mesh reconstructed from the Gaussian splat (vertex colours + faces), same canonical frame."""
    from app.metaverse.point_cloud import VIEWER_MESH_PATH, build_scene_mesh

    try:
        path = build_scene_mesh()
    except FileNotFoundError:
        path = VIEWER_MESH_PATH
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Boiler room mesh not found on server")
    return FileResponse(path=str(path), media_type="application/octet-stream", filename=path.name)


@router.post("/vision/analyze")
async def analyze_viewport_view(
    file: UploadFile = File(...),
    classes: str = Form(default=""),
    confidence: float = Form(default=0.15, ge=0.01, le=0.95),
):
    """Run open-vocabulary YOLO-World object detection on viewport snapshot."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Image upload required.",
        )
    image_bytes = await file.read()
    requested_classes = [c.strip() for c in classes.split(",") if c.strip()]
    try:
        return analyze_image(image_bytes, requested_classes, confidence)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"YOLO-World analysis unavailable: {exc}",
        )


@router.post("/copilot/query", response_model=CopilotQueryResponse)
def copilot_query(
    request: CopilotQueryRequest,
    session: Session = Depends(get_session),
):
    """Evidence-grounded diagnosis: telemetry drift, alarms, similar cases, docs and data quality."""
    asset = get_asset_or_404(session, request.asset_id)
    state = crud.get_asset_state(session, asset.asset_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No current state for {asset.asset_id}.")

    doc_ids = [state.knowledge_doc_id, *COPILOT_GUIDANCE_DOCS]
    docs = session.exec(select(KnowledgeDoc).where(KnowledgeDoc.doc_id.in_(doc_ids))).all()
    cases = session.exec(select(HistoricalServiceCase).where(HistoricalServiceCase.asset_class == asset.asset_class)).all()
    dq_issues = session.exec(select(DataQuality).where(DataQuality.asset_id == asset.asset_id)).all()
    frame = get_scene().find_frame(asset.asset_id)
    mapping_confidence = None
    if frame is not None:
        mapping_confidence = frame["mapping_confidence"]

    return get_copilot().diagnose_asset(
        asset=asset.model_dump(),
        state=state.model_dump(),
        telemetry=[t.model_dump() for t in crud.get_asset_telemetry(session, asset.asset_id, limit=COPILOT_TELEMETRY_WINDOW)],
        events=[e.model_dump() for e in crud.get_asset_events(session, asset.asset_id, limit=50)],
        work_orders=[w.model_dump() for w in crud.get_asset_work_orders(session, asset.asset_id, limit=20)],
        docs=[d.model_dump() for d in docs],
        cases=[c.model_dump() for c in cases],
        dq_issues=[q.model_dump() for q in dq_issues],
        mapping_confidence=mapping_confidence,
        question=request.prompt or request.query,
    )
