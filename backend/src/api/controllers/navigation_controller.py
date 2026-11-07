from typing import Optional

from fastapi import Depends, Query

from api.container import Container, get_container
from api.controllers.errors import http_errors
from dto.navigation_dto import NavigationPathResponse, WalkableGridResponse


def get_navigation_path(
    target_id: Optional[str] = Query(None, description="Asset ID, tag or object ID; defaults to the faulty target"),
    start_x: Optional[float] = Query(None),
    start_z: Optional[float] = Query(None),
    goal_x: Optional[float] = Query(None, description="Floor point to walk to (click-to-walk); overrides target_id"),
    goal_z: Optional[float] = Query(None),
    app: Container = Depends(get_container),
) -> NavigationPathResponse:
    """Collision-free route from the entry (or start_x/start_z) to the target, or to a floor point."""
    start = (start_x, start_z) if start_x is not None and start_z is not None else None
    goal = (goal_x, goal_z) if goal_x is not None and goal_z is not None else None
    with http_errors():
        return NavigationPathResponse.model_validate(app.navigation.path(target_id, start, goal))



def get_walkable_grid(app: Container = Depends(get_container)) -> WalkableGridResponse:
    """The navigation occupancy grid, for the walkable-floor overlay and camera collision."""
    return WalkableGridResponse.model_validate(app.navigation.walkable())
