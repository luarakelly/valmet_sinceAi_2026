"""Navigation use case: collision-checked route to an asset or object."""

from typing import Any, Dict, Optional, Tuple

from business.errors import NotFoundError, RouteNotFoundError
from business.interfaces.ports.outbound import SceneEngine


class NavigationService:
    def __init__(self, scene: SceneEngine):
        self._scene = scene

    def path(self, target_id: Optional[str] = None, start: Optional[Tuple[float, float]] = None) -> Dict[str, Any]:
        try:
            return self._scene.get_navigation_path(target_id=target_id, start=start)
        except KeyError:
            raise NotFoundError("No scene object matches '{}'.".format(target_id))
        except Exception as error:  # adapter-specific "no route" exception
            if type(error).__name__ == "RouteNotFound":
                raise RouteNotFoundError("No collision-free route to '{}'.".format(target_id)) from error
            raise
