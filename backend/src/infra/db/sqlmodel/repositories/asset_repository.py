"""SQLModel implementation of the business AssetRepository port.

Returns plain dicts (model_dump) so the business layer never sees SQLModel tables.
"""

from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional

from sqlalchemy import func
from sqlmodel import Session, select

from business.interfaces.ports.outbound.asset_repository import AssetRepository
from infra.db.sqlmodel.tables import (
    AlarmEvent,
    AssetMaster,
    CurrentState,
    DataQuality,
    HistoricalServiceCase,
    KnowledgeDoc,
    MaintenanceHistory,
    TelemetrySample,
)


def _dump(rows) -> List[dict]:
    return [row.model_dump() for row in rows]


class SqlModelAssetRepository(AssetRepository):
    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def find(self, identifier: str) -> Optional[dict]:
        key = identifier.strip().lower()
        with self._session_factory() as session:
            row = session.exec(
                select(AssetMaster).where(
                    (func.lower(AssetMaster.asset_id) == key) | (func.lower(AssetMaster.tag) == key)
                )
            ).first()
            return row.model_dump() if row else None

    def list(self, area_id=None, asset_class=None, criticality=None, search=None) -> List[dict]:
        stmt = select(AssetMaster)
        if area_id:
            stmt = stmt.where(AssetMaster.area_id == area_id.strip())
        if asset_class:
            stmt = stmt.where(func.lower(AssetMaster.asset_class) == asset_class.strip().lower())
        if criticality:
            stmt = stmt.where(func.lower(AssetMaster.criticality).like(f"%{criticality.strip().lower()}%"))
        if search:
            kw = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                func.lower(AssetMaster.tag).like(kw)
                | func.lower(AssetMaster.area_name).like(kw)
                | func.lower(AssetMaster.asset_id).like(kw)
            )
        with self._session_factory() as session:
            return _dump(session.exec(stmt.order_by(AssetMaster.asset_id.asc())).all())

    def states(self, asset_ids: Optional[Iterable[str]] = None) -> Dict[str, dict]:
        stmt = select(CurrentState)
        if asset_ids is not None:
            ids = list(asset_ids)
            if not ids:
                return {}
            stmt = stmt.where(CurrentState.asset_id.in_(ids))
        with self._session_factory() as session:
            return {row.asset_id: row.model_dump() for row in session.exec(stmt).all()}

    def telemetry_range(self, asset_id: str, limit: int, start: Optional[datetime] = None, end: Optional[datetime] = None) -> List[dict]:
        stmt = select(TelemetrySample).where(TelemetrySample.asset_id == asset_id)
        if start:
            stmt = stmt.where(TelemetrySample.timestamp >= start)
        if end:
            stmt = stmt.where(TelemetrySample.timestamp <= end)
        with self._session_factory() as session:
            return _dump(session.exec(stmt.order_by(TelemetrySample.timestamp.asc()).limit(limit)).all())

    def recent_telemetry(self, asset_id: str, limit: int) -> List[dict]:
        stmt = (
            select(TelemetrySample)
            .where(TelemetrySample.asset_id == asset_id)
            .order_by(TelemetrySample.timestamp.desc())
            .limit(limit)
        )
        with self._session_factory() as session:
            return list(reversed(_dump(session.exec(stmt).all())))

    def events(self, asset_id: str, limit: int, severity=None, event_type=None, status=None) -> List[dict]:
        stmt = select(AlarmEvent).where(AlarmEvent.asset_id == asset_id)
        if severity:
            stmt = stmt.where(func.lower(AlarmEvent.severity) == severity.strip().lower())
        if event_type:
            stmt = stmt.where(func.lower(AlarmEvent.event_type) == event_type.strip().lower())
        if status:
            stmt = stmt.where(func.lower(AlarmEvent.status) == status.strip().lower())
        with self._session_factory() as session:
            return _dump(session.exec(stmt.order_by(AlarmEvent.timestamp.desc()).limit(limit)).all())

    def work_orders(self, asset_id: str, limit: int) -> List[dict]:
        stmt = (
            select(MaintenanceHistory)
            .where(MaintenanceHistory.asset_id == asset_id)
            .order_by(MaintenanceHistory.opened_at.desc())
            .limit(limit)
        )
        with self._session_factory() as session:
            return _dump(session.exec(stmt).all())

    def documents(self, doc_ids: Iterable[str] = (), scopes: Iterable[str] = ()) -> List[dict]:
        ids = [d for d in doc_ids if d]
        scope_list = [s for s in scopes if s]
        if not ids and not scope_list:
            return []
        condition = None
        if ids:
            condition = KnowledgeDoc.doc_id.in_(ids)
        if scope_list:
            scope_condition = KnowledgeDoc.scope.in_(scope_list)
            condition = scope_condition if condition is None else (condition | scope_condition)
        with self._session_factory() as session:
            return _dump(session.exec(select(KnowledgeDoc).where(condition)).all())

    def service_cases(self, asset_class: str) -> List[dict]:
        with self._session_factory() as session:
            return _dump(session.exec(select(HistoricalServiceCase).where(HistoricalServiceCase.asset_class == asset_class)).all())

    def data_quality(self, asset_id: str) -> List[dict]:
        with self._session_factory() as session:
            return _dump(session.exec(select(DataQuality).where(DataQuality.asset_id == asset_id)).all())

    def add_work_order(self, record: dict) -> dict:
        with self._session_factory() as session:
            row = MaintenanceHistory(**record)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.model_dump()

    def counts(self) -> Dict[str, int]:
        with self._session_factory() as session:
            return {
                "assets": session.scalar(select(func.count(AssetMaster.asset_id))) or 0,
                "telemetry": session.scalar(select(func.count(TelemetrySample.id))) or 0,
                "events": session.scalar(select(func.count(AlarmEvent.event_id))) or 0,
                "high_events": session.scalar(select(func.count(AlarmEvent.event_id)).where(AlarmEvent.severity == "high")) or 0,
                "work_orders": session.scalar(select(func.count(MaintenanceHistory.work_order_id))) or 0,
                "data_quality": session.scalar(select(func.count(DataQuality.issue_id))) or 0,
            }
