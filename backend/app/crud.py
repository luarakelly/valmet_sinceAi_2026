"""Read helpers shared by routes: newest-first evidence queries per asset."""

from typing import List, Optional

from sqlmodel import Session, select

from app.models import AlarmEvent, CurrentState, MaintenanceHistory, TelemetrySample


def get_asset_state(session: Session, asset_id: str) -> Optional[CurrentState]:
    return session.get(CurrentState, asset_id)


def get_asset_telemetry(session: Session, asset_id: str, limit: int = 100) -> List[TelemetrySample]:
    """Most recent `limit` samples, returned oldest first."""
    stmt = (
        select(TelemetrySample)
        .where(TelemetrySample.asset_id == asset_id)
        .order_by(TelemetrySample.timestamp.desc())
        .limit(limit)
    )
    return list(reversed(session.exec(stmt).all()))


def get_asset_events(session: Session, asset_id: str, limit: int = 50) -> List[AlarmEvent]:
    stmt = select(AlarmEvent).where(AlarmEvent.asset_id == asset_id).order_by(AlarmEvent.timestamp.desc()).limit(limit)
    return list(session.exec(stmt).all())


def get_asset_work_orders(session: Session, asset_id: str, limit: int = 20) -> List[MaintenanceHistory]:
    stmt = (
        select(MaintenanceHistory)
        .where(MaintenanceHistory.asset_id == asset_id)
        .order_by(MaintenanceHistory.opened_at.desc())
        .limit(limit)
    )
    return list(session.exec(stmt).all())
