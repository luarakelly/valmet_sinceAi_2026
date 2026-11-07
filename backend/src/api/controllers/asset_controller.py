from datetime import datetime
from typing import List, Optional

from fastapi import Depends, Query

from api.container import Container, get_container
from api.controllers.errors import http_errors
from dto.asset_dto import (
    AlarmEventRead,
    AssetDetailRead,
    AssetRead,
    KnowledgeDocRead,
    MaintenanceHistoryRead,
    TelemetryRead,
)


def list_assets(
    area_id: Optional[str] = Query(None, description="Filter by area code (e.g. AREA-01 to AREA-05)"),
    asset_class: Optional[str] = Query(None, description="Filter by class (CONTROL_VALVE, PROCESS_PUMP, ELECTRIC_MOTOR, etc.)"),
    criticality: Optional[str] = Query(None, description="Filter by criticality (A - production critical, B, C)"),
    condition_state: Optional[str] = Query(None, description="Filter by condition (healthy, watch, degraded, attention_required)"),
    search: Optional[str] = Query(None, description="Search keyword matching tag, area_name, or asset_id"),
    app: Container = Depends(get_container),
) -> List[AssetRead]:
    """List assets with embedded current health state and 3D spatial anchor coordinates."""
    rows = app.assets.list_assets(area_id, asset_class, criticality, condition_state, search)
    return [AssetRead.model_validate(row) for row in rows]


def get_asset_detail(id: str, app: Container = Depends(get_container)) -> AssetDetailRead:
    """Full 360° asset detail by asset_id (e.g. ASSET-017) or tag (e.g. P-005)."""
    with http_errors():
        return AssetDetailRead.model_validate(app.assets.detail(id))


def get_asset_telemetry(
    id: str,
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum samples to return"),
    start_time: Optional[datetime] = Query(None, description="Filter samples on or after ISO timestamp"),
    end_time: Optional[datetime] = Query(None, description="Filter samples on or before ISO timestamp"),
    app: Container = Depends(get_container),
) -> List[TelemetryRead]:
    """Time-series telemetry samples for an asset, oldest first."""
    with http_errors():
        return [TelemetryRead.model_validate(r) for r in app.assets.telemetry(id, limit, start_time, end_time)]


def get_asset_events(
    id: str,
    limit: int = Query(default=50, ge=1, le=500, description="Maximum events to return"),
    severity: Optional[str] = Query(None, description="Filter by severity: low, medium, high"),
    event_type: Optional[str] = Query(None, description="Filter by event type (e.g. CONDITION_CHANGE, DIAGNOSTIC_ALERT)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (open, acknowledged, closed)"),
    app: Container = Depends(get_container),
) -> List[AlarmEventRead]:
    """Recent alarms and events for an asset, newest first."""
    with http_errors():
        rows = app.assets.events(id, limit, severity, event_type, status_filter)
        return [AlarmEventRead.model_validate(r) for r in rows]


def get_asset_documents(id: str, app: Container = Depends(get_container)) -> List[KnowledgeDocRead]:
    """RAG-ready engineering docs and safety guardrails applicable to an asset."""
    with http_errors():
        return [KnowledgeDocRead.model_validate(d) for d in app.assets.documents(id)]


def get_asset_work_orders(
    id: str,
    limit: int = Query(default=20, ge=1, le=100),
    app: Container = Depends(get_container),
) -> List[MaintenanceHistoryRead]:
    """Maintenance history and service records for an asset."""
    with http_errors():
        return [MaintenanceHistoryRead.model_validate(w) for w in app.assets.work_orders(id, limit)]
