"""Ask Your Factory - Database Engine & Ingestion Pipeline.

Orchestrates database connection, session generation, schema creation,
and robust, idempotent ingestion of all 10 entities from the Ask Your Factory data pack:
1. KnowledgeDoc (8 documents)
2. AssetMaster / Asset (30 equipment master records)
3. SceneAnchor (30 spatial 3D bounding anchors)
4. CurrentState (30 health and condition states)
5. HistoricalServiceCase (50 reference diagnostic cases)
6. MaintenanceHistory (300 past work orders)
7. AlarmEvent (1,000 synthetic events and alerts)
8. DataQuality (120 synthetic data anomalies)
9. RAGCorpusIndex (38 markdown documentation entries)
10. TelemetrySample / Telemetry (4,320 multivariate 30-min time-series samples)
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Generator
from contextlib import contextmanager

from sqlalchemy import event, text, select, func, delete
from sqlmodel import SQLModel, create_engine, Session

logger = logging.getLogger("ask_your_factory_database")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

DB_FILE = BASE_DIR / "database.db"
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DB_FILE}"
DB_URL = DATABASE_URL

is_sqlite = DATABASE_URL.startswith("sqlite")
if is_sqlite:
    connect_args = {"check_same_thread": False}
else:
    connect_args = {}

engine = create_engine(
    DATABASE_URL,
    echo=False,  # Suppress console flooding on 4,320 telemetry rows
    connect_args=connect_args,
)

if is_sqlite:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.close()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency for yielding database sessions."""
    with Session(engine) as session:
        yield session


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for standalone scripts, background tasks, and tests."""
    with Session(engine) as session:
        yield session



def parse_datetime(val: Any) -> Optional[datetime]:
    """Robustly parse ISO datetime strings, timestamps, or datetime objects with UTC timezone."""
    if val is None or val == "" or val == "None":
        return None
    if isinstance(val, datetime):
        if val.tzinfo:
            return val
        return val.replace(tzinfo=timezone.utc)
    if isinstance(val, str):
        val_clean = val.strip()
        if not val_clean:
            return None
        try:
            s = val_clean.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo:
                return dt
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(val_clean, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
    return None


def parse_float(val: Any) -> Optional[float]:
    """Robustly cast numeric or string values to float, returning None for empty/null."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val_clean = val.strip()
        if val_clean in ("", "None", "nan", "NaN", "null", "-"):
            return None
        try:
            return float(val_clean)
        except ValueError:
            return None
    return None


def parse_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    """Robustly cast numeric or string values to integer."""
    if val is None:
        return default
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        val_clean = val.strip()
        if val_clean in ("", "None", "nan", "NaN", "null", "-"):
            return default
        try:
            return int(float(val_clean))
        except ValueError:
            return default
    return default


def parse_bool(val: Any, default: bool = True) -> bool:
    """Robustly parse boolean flags from bool, int, or string."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("true", "1", "yes", "t"):
            return True
        if v in ("false", "0", "no", "f"):
            return False
    return default



def ingest_valmet_data(session: Optional[Session] = None, force: bool = False) -> Dict[str, Any]:
    """Topologically ingests all 10 entity sheets into the SQLModel database.
    
    Topological Order:
    1. KnowledgeDoc (zero dependencies)
    2. AssetMaster (root equipment entity)
    3. SceneAnchor (references AssetMaster)
    4. CurrentState (references AssetMaster & KnowledgeDoc)
    5. HistoricalServiceCase (references KnowledgeDoc)
    6. MaintenanceHistory (references AssetMaster & KnowledgeDoc)
    7. AlarmEvent (references AssetMaster)
    8. DataQuality (references AssetMaster)
    9. RAGCorpusIndex (references AssetMaster optionally)
    10. TelemetrySample (references AssetMaster, inserted in 500-item chunks)
    """
    from app.models import (
        AssetMaster,
        SceneAnchor,
        CurrentState,
        TelemetrySample,
        AlarmEvent,
        MaintenanceHistory,
        KnowledgeDoc,
        HistoricalServiceCase,
        DataQuality,
        RAGCorpusIndex,
    )
    from app.metaverse.dataset import get_dataset

    owns_session = session is None
    if owns_session:
        session = Session(engine)

    try:
        existing_assets = session.scalar(select(func.count(AssetMaster.asset_id))) or 0
        if existing_assets >= 30 and not force:
            logger.info(f"Database already populated ({existing_assets} assets present). Skipping ingestion.")
            return {"status": "skipped", "reason": "already_populated", "assets_count": existing_assets}

        if force and existing_assets > 0:
            logger.info("Force re-ingestion requested. Purging existing records in reverse topological order...")
            for model in [
                TelemetrySample,
                RAGCorpusIndex,
                DataQuality,
                AlarmEvent,
                MaintenanceHistory,
                HistoricalServiceCase,
                CurrentState,
                SceneAnchor,
                AssetMaster,
                KnowledgeDoc,
            ]:
                session.exec(delete(model))
            session.commit()
            logger.info("Purge complete.")

        dataset = get_dataset()
        data = dataset.data
        if not data or "Asset_Master" not in data:
            raise RuntimeError("Failed to load dataset: 'Asset_Master' sheet not found in data pack.")

        stats: Dict[str, int] = {}

        docs_raw = data.get("Knowledge_Docs", [])
        docs = [
            KnowledgeDoc(
                doc_id=r["doc_id"],
                title=r["title"],
                scope=r["scope"],
                content=r["content"],
                synthetic_record=parse_bool(r.get("synthetic_record"), True),
            )
            for r in docs_raw
        ]
        session.add_all(docs)
        session.flush()
        stats["KnowledgeDoc"] = len(docs)

        assets_raw = data.get("Asset_Master", [])
        assets = [
            AssetMaster(
                asset_id=r["asset_id"],
                tag=r["tag"],
                asset_class=r["asset_class"],
                area_id=r["area_id"],
                area_name=r["area_name"],
                process_context=r.get("process_context"),
                criticality=r["criticality"],
                installation_date=parse_datetime(r.get("installation_date")),
                last_service_date=parse_datetime(r.get("last_service_date")),
                service_interval_days=parse_int(r.get("service_interval_days"), 180),
                connectivity_profile=r.get("connectivity_profile", "OPC_UA"),
                scene_anchor_id=r.get("scene_anchor_id"),
                qr_id=r.get("qr_id"),
                nfc_id=r.get("nfc_id"),
                data_classification=r.get("data_classification", "SYNTHETIC"),
                synthetic_record=parse_bool(r.get("synthetic_record"), True),
            )
            for r in assets_raw
        ]
        session.add_all(assets)
        session.flush()
        stats["AssetMaster"] = len(assets)

        anchors_raw = data.get("Scene_Anchors", [])
        anchors = [
            SceneAnchor(
                scene_anchor_id=r["scene_anchor_id"],
                asset_id=r["asset_id"],
                tag=r["tag"],
                area_id=r["area_id"],
                x_local_m=parse_float(r["x_local_m"]) or 0.0,
                y_local_m=parse_float(r["y_local_m"]) or 0.0,
                z_local_m=parse_float(r["z_local_m"]) or 0.0,
                bbox_x_m=parse_float(r.get("bbox_x_m")) or 1.0,
                bbox_y_m=parse_float(r.get("bbox_y_m")) or 1.0,
                bbox_z_m=parse_float(r.get("bbox_z_m")) or 1.0,
                scene_path=r.get("scene_path"),
                mapping_status=r.get("mapping_status", "placeholder_until_valmet_scene_received"),
                identity_methods=r.get("identity_methods", "asset_id / QR / NFC / manual mapping"),
                mapping_confidence=parse_float(r.get("mapping_confidence")) or 0.65,
                remap_instruction=r.get("remap_instruction"),
                synthetic_record=parse_bool(r.get("synthetic_record"), True),
            )
            for r in anchors_raw
        ]
        session.add_all(anchors)
        session.flush()
        stats["SceneAnchor"] = len(anchors)

        states_raw = data.get("Current_State", [])
        states = [
            CurrentState(
                asset_id=r["asset_id"],
                tag=r["tag"],
                asset_class=r["asset_class"],
                area_name=r["area_name"],
                criticality=r["criticality"],
                health_score=parse_float(r["health_score"]) or 100.0,
                condition_state=r["condition_state"],
                issue_code=r["issue_code"],
                issue_summary=r.get("issue_summary"),
                urgency=r.get("urgency", "routine"),
                recommended_next_check=r.get("recommended_next_check"),
                model_confidence=parse_float(r.get("model_confidence")) or 0.85,
                last_updated=parse_datetime(r.get("last_updated")) or datetime.now(timezone.utc),
                knowledge_doc_id=r.get("knowledge_doc_id"),
                synthetic_record=parse_bool(r.get("synthetic_record"), True),
            )
            for r in states_raw
        ]
        session.add_all(states)
        session.flush()
        stats["CurrentState"] = len(states)

        cases_raw = data.get("Historical_Service_Cases", [])
        cases = [
            HistoricalServiceCase(
                case_id=r["case_id"],
                asset_class=r["asset_class"],
                historical_issue_code=r["historical_issue_code"],
                historical_interpretation=r["historical_interpretation"],
                recommended_next_check=r["recommended_next_check"],
                safe_evidence_workflow=r["safe_evidence_workflow"],
                severity=r["severity"],
                knowledge_doc_id=r.get("knowledge_doc_id"),
                fairness_note=r.get("fairness_note"),
                synthetic_record=parse_bool(r.get("synthetic_record"), True),
            )
            for r in cases_raw
        ]
        session.add_all(cases)
        session.flush()
        stats["HistoricalServiceCase"] = len(cases)

        maint_raw = data.get("Maintenance_History", [])
        wos = [
            MaintenanceHistory(
                work_order_id=r["work_order_id"],
                asset_id=r["asset_id"],
                tag=r["tag"],
                area_name=r["area_name"],
                opened_at=parse_datetime(r["opened_at"]) or datetime.now(timezone.utc),
                action=r["action"],
                maintenance_type=r.get("maintenance_type", "preventive"),
                priority=r.get("priority", "medium"),
                result=r.get("result", "service_completed"),
                duration_h=parse_float(r.get("duration_h")) or 1.0,
                downtime_h=parse_float(r.get("downtime_h")) or 0.0,
                role=r.get("role", "field_technician"),
                knowledge_doc_id=r.get("knowledge_doc_id"),
                synthetic_record=parse_bool(r.get("synthetic_record"), True),
            )
            for r in maint_raw
        ]
        session.add_all(wos)
        session.flush()
        stats["MaintenanceHistory"] = len(wos)

        events_raw = data.get("Alarms_Events", [])
        events = [
            AlarmEvent(
                event_id=r["event_id"],
                timestamp=parse_datetime(r["timestamp"]) or datetime.now(timezone.utc),
                asset_id=r["asset_id"],
                tag=r["tag"],
                area_name=r["area_name"],
                event_type=r.get("event_type", "DIAGNOSTIC_ALERT"),
                severity=r.get("severity", "medium"),
                event_code=r.get("event_code", "ALERT"),
                description=r["description"],
                source=r.get("source", "edge_sensor"),
                status=r.get("status", "open"),
                synthetic_record=parse_bool(r.get("synthetic_record"), True),
            )
            for r in events_raw
        ]
        session.add_all(events)
        session.flush()
        stats["AlarmEvent"] = len(events)

        dq_raw = data.get("Data_Quality", [])
        dqs = [
            DataQuality(
                issue_id=r["issue_id"],
                asset_id=r["asset_id"],
                tag=r["tag"],
                issue_type=r["issue_type"],
                severity=r["severity"],
                source_sheet=r.get("source_sheet", "Telemetry"),
                recommended_handling=r.get("recommended_handling", "flag_for_review"),
                synthetic_record=parse_bool(r.get("synthetic_record"), True),
            )
            for r in dq_raw
        ]
        session.add_all(dqs)
        session.flush()
        stats["DataQuality"] = len(dqs)

        rag_raw = data.get("RAG_Corpus_Index", [])
        rags = []
        for r in rag_raw:
            raw_aid = r.get("asset_id")
            if raw_aid:
                rag_asset_id = raw_aid
            else:
                rag_asset_id = None

            raw_tag = r.get("tag")
            if raw_tag:
                rag_tag = raw_tag
            else:
                rag_tag = None

            rags.append(
                RAGCorpusIndex(
                    doc_id=r["doc_id"],
                    asset_id=rag_asset_id,
                    tag=rag_tag,
                    scope=r["scope"],
                    file_name=r["file_name"],
                    mime_type=r.get("mime_type", "text/markdown"),
                    document_role=r.get("document_role", "asset_card"),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
            )
        session.add_all(rags)
        session.flush()
        stats["RAGCorpusIndex"] = len(rags)

        telem_raw = data.get("Telemetry_Sample_3d", [])
        batch_size = 500
        telemetry_count = 0

        for i in range(0, len(telem_raw), batch_size):
            chunk = telem_raw[i : i + batch_size]
            telem_objs = [
                TelemetrySample(
                    timestamp=parse_datetime(r["timestamp"]) or datetime.now(timezone.utc),
                    asset_id=r["asset_id"],
                    tag=r["tag"],
                    asset_class=r["asset_class"],
                    area_id=r["area_id"],
                    process_pressure_bar=parse_float(r.get("process_pressure_bar")),
                    process_flow_pct=parse_float(r.get("process_flow_pct")),
                    position_setpoint_pct=parse_float(r.get("position_setpoint_pct")),
                    position_actual_pct=parse_float(r.get("position_actual_pct")),
                    pneumatic_supply_bar=parse_float(r.get("pneumatic_supply_bar")),
                    stiction_index=parse_float(r.get("stiction_index")),
                    load_for_opening_pct=parse_float(r.get("load_for_opening_pct")),
                    vibration_mm_s=parse_float(r.get("vibration_mm_s")),
                    bearing_temp_c=parse_float(r.get("bearing_temp_c")),
                    motor_current_a=parse_float(r.get("motor_current_a")),
                    speed_rpm=parse_float(r.get("speed_rpm")),
                    signal_quality_pct=parse_float(r.get("signal_quality_pct")) or 99.0,
                    sensor_bias=parse_float(r.get("sensor_bias")),
                    source_profile=r.get("source_profile", "simulated_30min_stream"),
                    synthetic_record=parse_bool(r.get("synthetic_record"), True),
                )
                for r in chunk
            ]
            session.add_all(telem_objs)
            session.flush()
            telemetry_count += len(telem_objs)

        stats["TelemetrySample"] = telemetry_count
        stats["total_records"] = sum(stats.values())

        session.commit()
        logger.info(f"Ingestion successful! Populated {stats['total_records']} total records: {stats}")
        return {"status": "success", "stats": stats}

    except Exception as e:
        session.rollback()
        logger.error(f"Ingestion pipeline failed: {e}", exc_info=True)
        raise
    finally:
        if owns_session:
            session.close()


def init_db(populate: bool = True) -> None:
    """Creates database tables and optionally populates Valmet dataset if empty."""
    import app.models  # noqa: F401

    logger.info(f"Initializing database tables at {DATABASE_URL}...")
    SQLModel.metadata.create_all(engine)
    logger.info("Database tables verified.")

    if populate:
        populate_db_if_empty()


def populate_db_if_empty(force: bool = False) -> Dict[str, Any]:
    """Populates the database if assets table is empty or if force=True."""
    with Session(engine) as session:
        return ingest_valmet_data(session=session, force=force)


if __name__ == "__main__":
    force_flag = "--force" in sys.argv
    print(f"Executing database init & ingestion (force={force_flag})...")
    init_db(populate=True)
    if force_flag:
        populate_db_if_empty(force=True)
    print("Database initialization complete.")
