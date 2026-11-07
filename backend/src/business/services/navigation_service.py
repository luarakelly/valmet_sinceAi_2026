"""Navigation use case: collision-checked route to an asset or object."""

from typing import Any, Dict, Optional, Tuple

from business.errors import NotFoundError, RouteNotFoundError
from business.interfaces.ports.outbound import SceneEngine


class NavigationService:
    def __init__(self, scene: SceneEngine):
        self._scene = scene

    def path(
        self,
        target_id: Optional[str] = None,
        start: Optional[Tuple[float, float]] = None,
        goal: Optional[Tuple[float, float]] = None,
    ) -> Dict[str, Any]:
        """Route to an asset/object, or to the floor point `goal` (click-to-walk)."""
        try:
            return self._scene.get_navigation_path(target_id=target_id, start=start, goal=goal)
        except KeyError:
            raise NotFoundError("No scene object matches '{}'.".format(target_id))
        except Exception as error:  # adapter-specific "no route" exception
            if type(error).__name__ == "RouteNotFound":
                raise RouteNotFoundError("No collision-free route to '{}'.".format(target_id or "that point")) from error
            raise


    def walkable(self) -> Dict[str, Any]:
        """Where the robot may walk (viewer overlay) and where obstacles are (camera collision)."""
        return self._scene.walkable_grid()
