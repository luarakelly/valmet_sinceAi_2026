from typing import List

from fastapi import Depends, Query

from api.container import Container, get_container
from dto.maintenance_dto import MaintenancePriorityRead


def get_maintenance_priorities(
    limit: int = Query(default=10, ge=1, le=30),
    attention_only: bool = Query(default=True),
    app: Container = Depends(get_container),
) -> List[MaintenancePriorityRead]:
    """Assets ranked by condition × criticality × urgency × model certainty."""
    return [MaintenancePriorityRead.model_validate(p) for p in app.maintenance.priorities(limit, attention_only)]
