"""FastAPI Router for the Ask Your Factory 3D Digital Twin."""

from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlmodel import Session

from app.db import get_session
from app import crud
from app.schemas import (
    AssetRead,
    AssetStateRead,
    SceneAnchorRead,
    TelemetryRead,
    AlarmEventRead,
    WorkOrderRead,
    KnowledgeDocRead,
    CopilotQueryRequest,
    CopilotQueryResponse,
    WorkOrderDraftRequest,
    WorkOrderDraftResponse,
)
from app.metaverse.copilot import get_copilot
from app.metaverse.scene_processor import get_scene

router = APIRouter(tags=["Ask Your Factory Digital Twin"])


@router.get("/assets", response_model=List[AssetRead])
def api_list_assets(session: Session = Depends(get_session)):
    """Retrieve all 30 industrial assets with bound state and 3D spatial anchor."""
    assets = crud.get_all_assets(session)
    result = []
    for a in assets:
        st = crud.get_asset_state(session, a.asset_id)
        anc = crud.get_asset_anchor(session, a.asset_id)
        item = a.model_dump()
        if st:
            item["state"] = st.model_dump()
        if anc:
            item["anchor"] = anc.model_dump()
        result.append(item)
    return result


@router.get("/assets/{asset_id}")
def api_get_asset(asset_id: str, session: Session = Depends(get_session)):
    """Retrieve detailed asset dossier including current state, anchor, and recent history."""
    asset = crud.get_asset_by_id(session, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset {asset_id} not found")
    st = crud.get_asset_state(session, asset.asset_id)
    anc = crud.get_asset_anchor(session, asset.asset_id)
    telem = crud.get_asset_telemetry(session, asset.asset_id, limit=50)
    evts = crud.get_asset_events(session, asset.asset_id, limit=10)
    wos = crud.get_asset_work_orders(session, asset.asset_id, limit=5)
    if st and st.knowledge_doc_id:
        doc = crud.get_knowledge_doc(session, st.knowledge_doc_id)
    else:
        doc = None

    if st:
        state_dump = st.model_dump()
    else:
        state_dump = None

    if anc:
        anchor_dump = anc.model_dump()
    else:
        anchor_dump = None

    if doc:
        doc_dump = doc.model_dump()
    else:
        doc_dump = None

    return {
        "asset": asset.model_dump(),
        "state": state_dump,
        "anchor": anchor_dump,
        "recent_telemetry": [t.model_dump() for t in telem],
        "recent_events": [e.model_dump() for e in evts],
        "work_orders": [w.model_dump() for w in wos],
        "knowledge_doc": doc_dump,
    }


@router.get("/assets/{asset_id}/telemetry", response_model=List[TelemetryRead])
def api_get_asset_telemetry(
    asset_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
):
    """Retrieve historical multivariate sensor telemetry stream for an asset."""
    records = crud.get_asset_telemetry(session, asset_id, limit=limit)
    return [r.model_dump() for r in records]


@router.get("/assets/{asset_id}/events", response_model=List[AlarmEventRead])
def api_get_asset_events(
    asset_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
):
    """Retrieve alarms, diagnostic alerts, and inspection notes for an asset."""
    events = crud.get_asset_events(session, asset_id, limit=limit)
    return [e.model_dump() for e in events]


@router.get("/assets/{asset_id}/work-orders", response_model=List[WorkOrderRead])
def api_get_asset_work_orders(
    asset_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    """Retrieve maintenance history and service records for an asset."""
    wos = crud.get_asset_work_orders(session, asset_id, limit=limit)
    return [w.model_dump() for w in wos]


@router.get("/assets/{asset_id}/documents")
def api_get_asset_doc(asset_id: str, session: Session = Depends(get_session)):
    """Retrieve authoritative RAG troubleshooting knowledge document for an asset."""
    st = crud.get_asset_state(session, asset_id)
    if st and st.knowledge_doc_id:
        doc_id = st.knowledge_doc_id
    else:
        doc_id = "DOC-FIELD-SAFETY"

    doc = crud.get_knowledge_doc(session, doc_id)
    if not doc:
        doc = crud.get_knowledge_doc(session, "DOC-FIELD-SAFETY")

    if doc:
        return doc.model_dump()
    return {"error": "Document not found"}


@router.get("/scene/anchors", response_model=List[SceneAnchorRead])
def api_get_scene_anchors(session: Session = Depends(get_session)):
    """Retrieve all 3D spatial anchor bounds and local coordinates."""
    anchors = crud.get_all_anchors(session)
    return [a.model_dump() for a in anchors]


@router.get("/scene/frames")
def api_get_semantic_frames():
    """Retrieve 50+ high-density 3D semantic bounding frames for all industrial equipment."""
    scene = get_scene()
    return scene.get_semantic_frames()


@router.post("/scene/extract-assets")
def api_extract_semantic_assets():
    """Execute live 3D spatial voxel clustering and semantic extraction over Industrial Boiler Room.ply."""
    scene = get_scene()
    return scene.run_algorithmic_extraction()


@router.get("/navigation/path")
def api_get_navigation_path(target_id: str = "ASSET-017"):
    """Retrieve collision-free obstacle-avoiding walking path for field avatar/robot to target asset."""
    scene = get_scene()
    return scene.get_navigation_path(target_id=target_id)


@router.get("/scene/boiler-room.ply")
def api_get_boiler_room_ply():
    """Serve standard Three.js PLY file with colored point cloud."""
    scene = get_scene()
    path = scene.get_ply_path()
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="3D PLY file not found on server")
    return FileResponse(
        path=str(path),
        media_type="application/octet-stream",
        filename="Industrial_Boiler_Room.ply",
    )


@router.get("/scene/raw-ply")
def api_get_raw_ply():
    """Stream raw 355 MB Industrial Boiler Room.ply if available."""
    scene = get_scene()
    if not scene.raw_path.exists():
        return FileResponse(path=str(scene.get_ply_path()), media_type="application/octet-stream")
    return FileResponse(path=str(scene.raw_path), media_type="application/octet-stream", filename="Industrial Boiler Room.ply")


@router.post("/copilot/query", response_model=CopilotQueryResponse)
def api_copilot_query(
    request: CopilotQueryRequest,
    session: Session = Depends(get_session),
):
    """Evidence-backed AI Diagnostics Copilot grounded in telemetry, events, work orders, and safety guidelines."""
    asset = crud.get_asset_by_id(session, request.asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset {request.asset_id} not found")
    st = crud.get_asset_state(session, asset.asset_id)
    telem = crud.get_asset_telemetry(session, asset.asset_id, limit=30)
    evts = crud.get_asset_events(session, asset.asset_id, limit=5)
    wos = crud.get_asset_work_orders(session, asset.asset_id, limit=3)
    if st and st.knowledge_doc_id:
        doc = crud.get_knowledge_doc(session, st.knowledge_doc_id)
    else:
        doc = None

    if st:
        state_dump = st.model_dump()
    else:
        state_dump = {}

    if doc:
        doc_dump = doc.model_dump()
    else:
        doc_dump = None

    copilot = get_copilot()
    diagnosis = copilot.diagnose_asset(
        asset=asset.model_dump(),
        state=state_dump,
        telemetry=[t.model_dump() for t in telem],
        events=[e.model_dump() for e in evts],
        work_orders=[w.model_dump() for w in wos],
        doc=doc_dump,
        custom_prompt=request.prompt,
    )
    return diagnosis


@router.post("/work-orders/draft", response_model=WorkOrderDraftResponse)
def api_draft_work_order(
    request: WorkOrderDraftRequest,
    session: Session = Depends(get_session),
):
    """Generate a formal field-service maintenance work order draft."""
    asset = crud.get_asset_by_id(session, request.asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset {request.asset_id} not found")
    st = crud.get_asset_state(session, asset.asset_id)
    if request.action:
        action = request.action
    else:
        if st:
            action = st.recommended_next_check
        else:
            action = "Inspect and verify equipment condition"

    if request.priority:
        wo_priority = request.priority
    else:
        wo_priority = "high"

    if st:
        wo_doc_id = st.knowledge_doc_id
    else:
        wo_doc_id = None

    wo = crud.create_work_order(
        session=session,
        asset_id=asset.asset_id,
        action=action,
        priority=wo_priority,
        doc_id=wo_doc_id,
    )

    safety = [
        "Obtain hot-work or mechanical entry permit before accessing pump or valve casing.",
        "Perform pneumatic/electrical Lockout-Tagout (LOTO).",
        "Wear mandatory eye protection, hard hat, and steel-toe footwear.",
    ]

    return {
        "work_order_id": wo.work_order_id,
        "asset_id": wo.asset_id,
        "tag": wo.tag,
        "area_name": wo.area_name,
        "action": wo.action,
        "maintenance_type": wo.maintenance_type,
        "priority": wo.priority,
        "recommended_role": wo.role,
        "estimated_duration_h": wo.duration_h,
        "status": "draft_created",
        "safety_instructions": safety,
        "created_at": wo.opened_at,
    }
