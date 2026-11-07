"""Inbound ports: the use cases the API (controllers) may call.

Each Protocol is implemented by the service of the same name in business/services.
"""

from typing import Any, Dict, List, Optional, Protocol, Tuple


class AssetQueries(Protocol):
    def list_assets(self, **filters: Any) -> List[Dict[str, Any]]: ...
    def detail(self, identifier: str) -> Dict[str, Any]: ...


class SceneQueries(Protocol):
    def frames(self) -> List[Dict[str, Any]]: ...
    def summary(self) -> Dict[str, Any]: ...


class NavigationUseCase(Protocol):
    def path(self, target_id: Optional[str], start: Optional[Tuple[float, float]]) -> Dict[str, Any]: ...


class CopilotUseCase(Protocol):
    def diagnose(self, identifier: str, question: Optional[str] = None) -> Dict[str, Any]: ...


class WorkOrderUseCase(Protocol):
    def draft(self, request: Dict[str, Any]) -> Dict[str, Any]: ...


class MaintenanceQueries(Protocol):
    def priorities(self, limit: int = 10) -> List[Dict[str, Any]]: ...
