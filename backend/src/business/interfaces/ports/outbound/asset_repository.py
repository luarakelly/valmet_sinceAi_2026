from datetime import datetime
from typing import Dict, Iterable, List, Optional, Protocol

from business.models.records import (
    AssetRecord,
    DataQualityRecord,
    DocumentRecord,
    EventRecord,
    ServiceCaseRecord,
    StateRecord,
    TelemetryRecord,
    WorkOrderRecord,
)


class AssetRepository(Protocol):
    """Read/write access to the imported builder pack."""

    def find(self, identifier: str) -> Optional[AssetRecord]:
        """By asset_id or tag, case-insensitive."""
        ...

    def list(
        self,
        area_id: Optional[str] = None,
        asset_class: Optional[str] = None,
        criticality: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[AssetRecord]:
        ...

    def states(self, asset_ids: Optional[Iterable[str]] = None) -> Dict[str, StateRecord]:
        ...

    def telemetry_range(
        self, asset_id: str, limit: int, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> List[TelemetryRecord]:
        """Oldest first, first `limit` samples in the range."""
        ...

    def recent_telemetry(self, asset_id: str, limit: int) -> List[TelemetryRecord]:
        """Latest `limit` samples, returned oldest first."""
        ...

    def events(
        self,
        asset_id: str,
        limit: int,
        severity: Optional[str] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[EventRecord]:
        """Newest first."""
        ...

    def work_orders(self, asset_id: str, limit: int) -> List[WorkOrderRecord]:
        """Newest first."""
        ...

    def documents(self, doc_ids: Iterable[str] = (), scopes: Iterable[str] = ()) -> List[DocumentRecord]:
        ...

    def service_cases(self, asset_class: str) -> List[ServiceCaseRecord]:
        ...

    def data_quality(self, asset_id: str) -> List[DataQualityRecord]:
        ...

    def add_work_order(self, record: WorkOrderRecord) -> WorkOrderRecord:
        ...

    def counts(self) -> Dict[str, int]:
        """assets, telemetry, events, high_events, work_orders, data_quality."""
        ...
