from typing import Optional, List, Dict, Any
from sqlmodel import Session, select
from hashlib import sha256
import uuid
from datetime import datetime

from app.models import (
    Catalog,
    Users,
    Asset,
    SceneAnchor,
    AssetState,
    AlarmEvent,
    MaintenanceWorkOrder,
    TelemetryRecord,
    KnowledgeDoc,
    DataQualityIssue,
)
from app.schemas import CatalogCreate
from app.metaverse.dataset import get_dataset


def save_db(session: Session, instance):
    session.add(instance)
    session.commit()
    session.refresh(instance)
    return instance


def _as_dict(obj):
    if not obj:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, dict):
        return obj
    return dict(obj)


# Legacy user methods
def create_user(session: Session, user: Optional[object] = None):
    data = _as_dict(user)
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if not name or not password or not email:
        return {"error": "name, email and password required"}

    hashed = sha256(password.encode("utf-8")).hexdigest()
    stmt = select(Users).where((Users.name == name) | (Users.email == email))
    existing = session.exec(stmt).first()
    if existing:
        return {"error": "username or email already exists"}

    user_obj = Users(name=name, email=email, password_hash=hashed)
    return save_db(session, user_obj)


def delete_user(session: Session, user: Optional[object] = None):
    data = _as_dict(user)
    name = data.get("name")
    password = data.get("password")

    if not name or not password:
        return {"error": "name and password required"}

    stmt = select(Users).where(Users.name == name)
    existing = session.exec(stmt).first()

    if existing:
        hashed = sha256(password.encode("utf-8")).hexdigest()
        if existing.password_hash == hashed:
            session.delete(existing)
            session.commit()
            return {"ok": True}
        return {"error": "wrong password"}
    return {"error": "user not found"}


def create_catalog_entry(session: Session, catalog_item: CatalogCreate) -> Catalog:
    data = _as_dict(catalog_item)
    name = data.get("name")
    type_ = data.get("type")

    stmt = select(Catalog).where(Catalog.name == name).where(Catalog.type == type_)
    existing = session.exec(stmt).first()
    if existing:
        return existing
    new_item = Catalog(**data)
    return save_db(session, new_item)


def get_catalog_entries(
    session: Session, type_: Optional[str] = None, limit: int = 100, offset: int = 0
):
    stmt = select(Catalog)
    if type_:
        stmt = stmt.where(Catalog.type == type_)
    stmt = stmt.limit(limit).offset(offset)
    return session.exec(stmt).all()


def get_catalog_entry_by_id(session: Session, item_id: uuid.UUID) -> Optional[Catalog]:
    return session.get(Catalog, item_id)


def delete_catalog_entry(session: Session, item: Catalog) -> None:
    session.delete(item)
    session.commit()


# =====================================================================
# Ask Your Factory CRUD & Auto-Seeder
# =====================================================================

def get_all_assets(session: Session) -> List[Asset]:
    return session.exec(select(Asset)).all()


def get_asset_by_id(session: Session, asset_id: str) -> Optional[Asset]:
    asset = session.get(Asset, asset_id)
    if not asset:
        asset = session.exec(select(Asset).where(Asset.tag == asset_id)).first()
    return asset


def get_asset_state(session: Session, asset_id: str) -> Optional[AssetState]:
    state = session.get(AssetState, asset_id)
    if not state:
        state = session.exec(select(AssetState).where(AssetState.tag == asset_id)).first()
    return state


def get_asset_anchor(session: Session, asset_id: str) -> Optional[SceneAnchor]:
    anchor = session.exec(select(SceneAnchor).where(SceneAnchor.asset_id == asset_id)).first()
    if not anchor:
        anchor = session.exec(select(SceneAnchor).where(SceneAnchor.tag == asset_id)).first()
    return anchor


def get_all_anchors(session: Session) -> List[SceneAnchor]:
    return session.exec(select(SceneAnchor)).all()


def get_asset_telemetry(session: Session, asset_id: str, limit: int = 100) -> List[TelemetryRecord]:
    stmt = select(TelemetryRecord).where(
        (TelemetryRecord.asset_id == asset_id) | (TelemetryRecord.tag == asset_id)
    ).order_by(TelemetryRecord.timestamp.desc()).limit(limit)
    records = session.exec(stmt).all()
    return list(reversed(records))


def get_asset_events(session: Session, asset_id: Optional[str] = None, limit: int = 50) -> List[AlarmEvent]:
    stmt = select(AlarmEvent)
    if asset_id:
        stmt = stmt.where((AlarmEvent.asset_id == asset_id) | (AlarmEvent.tag == asset_id))
    stmt = stmt.order_by(AlarmEvent.timestamp.desc()).limit(limit)
    return session.exec(stmt).all()


def get_asset_work_orders(session: Session, asset_id: Optional[str] = None, limit: int = 20) -> List[MaintenanceWorkOrder]:
    stmt = select(MaintenanceWorkOrder)
    if asset_id:
        stmt = stmt.where((MaintenanceWorkOrder.asset_id == asset_id) | (MaintenanceWorkOrder.tag == asset_id))
    stmt = stmt.order_by(MaintenanceWorkOrder.opened_at.desc()).limit(limit)
    return session.exec(stmt).all()


def get_knowledge_doc(session: Session, doc_id: str) -> Optional[KnowledgeDoc]:
    return session.get(KnowledgeDoc, doc_id)


def get_all_knowledge_docs(session: Session) -> List[KnowledgeDoc]:
    return session.exec(select(KnowledgeDoc)).all()


def create_work_order(
    session: Session,
    asset_id: str,
    action: str,
    priority: str = "high",
    maintenance_type: str = "corrective",
    role: str = "field_technician",
    duration_h: float = 2.0,
    downtime_h: float = 0.5,
    doc_id: Optional[str] = None,
) -> MaintenanceWorkOrder:
    asset = get_asset_by_id(session, asset_id)
    if asset:
        tag = asset.tag
        area = asset.area_name
    else:
        tag = asset_id
        area = "Industrial Boiler Room"
    wo_id = f"WO-AUTO-{uuid.uuid4().hex[:6].upper()}"

    wo = MaintenanceWorkOrder(
        work_order_id=wo_id,
        asset_id=asset_id,
        tag=tag,
        area_name=area,
        opened_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        action=action,
        maintenance_type=maintenance_type,
        priority=priority,
        result="draft_submitted",
        duration_h=duration_h,
        downtime_h=downtime_h,
        role=role,
        knowledge_doc_id=doc_id,
        synthetic_record=True,
    )
    return save_db(session, wo)


def seed_metaverse_data(session: Session) -> None:
    """Populates SQLModel tables from the Valmet builder pack if not already seeded."""
    existing_asset = session.exec(select(Asset)).first()
    if existing_asset is not None:
        return

    ds = get_dataset()
    data = ds.data
    if not data:
        return

    # 1. Assets
    for a in data.get("Asset_Master", []):
        session.add(Asset(
            asset_id=a["asset_id"],
            tag=a["tag"],
            asset_class=a["asset_class"],
            area_id=a["area_id"],
            area_name=a["area_name"],
            process_context=a.get("process_context"),
            criticality=a.get("criticality", "C - standard"),
            installation_date=str(a.get("installation_date", "")),
            last_service_date=str(a.get("last_service_date", "")),
            service_interval_days=int(a.get("service_interval_days") or 180),
            connectivity_profile=a.get("connectivity_profile"),
            scene_anchor_id=a.get("scene_anchor_id"),
            qr_id=a.get("qr_id"),
            nfc_id=a.get("nfc_id"),
        ))

    # 2. Scene Anchors (remapped and fitted to actual boiler room envelope [-4.5 to +4.0m])
    for anc in data.get("Scene_Anchors", []):
        # Scale coordinates to fit the actual ~8m x 3m x 6m boiler room envelope
        raw_x = float(anc.get("x_local_m", 0.0))
        raw_y = float(anc.get("y_local_m", 0.0))
        raw_z = float(anc.get("z_local_m", 0.0))
        # Normalized remapping from 0-30m range into boiler room coordinates [-4.0m, +3.5m]
        norm_x = round(((raw_x / 30.5) * 7.0) - 3.5, 2)
        norm_y = round(-0.85 + (raw_z * 0.45), 2)  # Elevation in boiler room
        norm_z = round(((raw_y / 16.0) * 4.5) - 3.8, 2)

        session.add(SceneAnchor(
            scene_anchor_id=anc["scene_anchor_id"],
            asset_id=anc["asset_id"],
            tag=anc["tag"],
            area_id=anc["area_id"],
            x_local_m=norm_x,
            y_local_m=norm_y,
            z_local_m=norm_z,
            bbox_x_m=float(anc.get("bbox_x_m", 1.0)),
            bbox_y_m=float(anc.get("bbox_y_m", 0.8)),
            bbox_z_m=float(anc.get("bbox_z_m", 1.0)),
            scene_path=anc.get("scene_path"),
            mapping_status="active_mapped",
            mapping_confidence=float(anc.get("mapping_confidence", 0.85)),
            remap_instruction=anc.get("remap_instruction"),
        ))

    # 3. Current State
    for s in data.get("Current_State", []):
        session.add(AssetState(
            asset_id=s["asset_id"],
            tag=s["tag"],
            asset_class=s["asset_class"],
            area_name=s["area_name"],
            criticality=s["criticality"],
            health_score=int(s.get("health_score", 100)),
            condition_state=s.get("condition_state", "healthy"),
            issue_code=s.get("issue_code", "NORMAL"),
            issue_summary=s.get("issue_summary", "No deviation"),
            urgency=s.get("urgency", "routine"),
            recommended_next_check=s.get("recommended_next_check", "monitor"),
            model_confidence=float(s.get("model_confidence", 0.9)),
            last_updated=str(s.get("last_updated", "")),
            knowledge_doc_id=s.get("knowledge_doc_id"),
        ))

    # 4. Alarms / Events
    for e in data.get("Alarms_Events", []):
        session.add(AlarmEvent(
            event_id=e["event_id"],
            timestamp=str(e["timestamp"]),
            asset_id=e["asset_id"],
            tag=e["tag"],
            area_name=e["area_name"],
            event_type=e["event_type"],
            severity=e["severity"],
            event_code=e["event_code"],
            description=e["description"],
            source=e["source"],
            status=e["status"],
        ))

    # 5. Work Orders
    for w in data.get("Maintenance_History", []):
        session.add(MaintenanceWorkOrder(
            work_order_id=w["work_order_id"],
            asset_id=w["asset_id"],
            tag=w["tag"],
            area_name=w["area_name"],
            opened_at=str(w["opened_at"]),
            action=w["action"],
            maintenance_type=w["maintenance_type"],
            priority=w["priority"],
            result=w["result"],
            duration_h=float(w.get("duration_h", 2.0)),
            downtime_h=float(w.get("downtime_h", 0.0)),
            role=w["role"],
            knowledge_doc_id=w.get("knowledge_doc_id"),
        ))

    # 6. Telemetry (Batch insert)
    for t in data.get("Telemetry_Sample_3d", []):
        def _f(val):
            if val is not None and val != "":
                return float(val)
            return None
        session.add(TelemetryRecord(
            timestamp=str(t["timestamp"]),
            asset_id=t["asset_id"],
            tag=t["tag"],
            asset_class=t["asset_class"],
            area_id=t["area_id"],
            process_pressure_bar=_f(t.get("process_pressure_bar")),
            process_flow_pct=_f(t.get("process_flow_pct")),
            position_setpoint_pct=_f(t.get("position_setpoint_pct")),
            position_actual_pct=_f(t.get("position_actual_pct")),
            pneumatic_supply_bar=_f(t.get("pneumatic_supply_bar")),
            stiction_index=_f(t.get("stiction_index")),
            load_for_opening_pct=_f(t.get("load_for_opening_pct")),
            vibration_mm_s=_f(t.get("vibration_mm_s")),
            bearing_temp_c=_f(t.get("bearing_temp_c")),
            motor_current_a=_f(t.get("motor_current_a")),
            speed_rpm=_f(t.get("speed_rpm")),
            signal_quality_pct=_f(t.get("signal_quality_pct")),
        ))

    # 7. Knowledge Docs
    for d in data.get("Knowledge_Docs", []):
        session.add(KnowledgeDoc(
            doc_id=d["doc_id"],
            title=d["title"],
            scope=d["scope"],
            content=d["content"],
        ))

    # 8. Data Quality Issues
    for dq in data.get("Data_Quality", []):
        session.add(DataQualityIssue(
            issue_id=dq["issue_id"],
            asset_id=dq["asset_id"],
            tag=dq["tag"],
            issue_type=dq["issue_type"],
            severity=dq["severity"],
            source_sheet=dq["source_sheet"],
            recommended_handling=dq["recommended_handling"],
        ))

    session.commit()
