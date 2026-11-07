from typing import Optional

from fastapi import Depends, Query

from api.container import Container, get_container
from api.controllers.errors import http_errors
from dto.navigation_dto import NavigationPathResponse


def get_navigation_path(
    target_id: Optional[str] = Query(None, description="Asset ID, tag or object ID; defaults to the faulty target"),
    start_x: Optional[float] = Query(None),
    start_z: Optional[float] = Query(None),
    app: Container = Depends(get_container),
) -> NavigationPathResponse:
    """Collision-free route from the entry (or start_x/start_z) to a standing spot beside the target."""
    start = (start_x, start_z) if start_x is not None and start_z is not None else None
    with http_errors():
        return NavigationPathResponse.model_validate(app.navigation.path(target_id, start))
