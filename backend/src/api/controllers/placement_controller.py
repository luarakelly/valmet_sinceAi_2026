from typing import Any, Dict

from fastapi import Depends

from api.container import Container, get_container
from api.controllers.errors import http_errors
from dto.placement_dto import LiftBoxRequest, PlacementBox


def lift_box(body: LiftBoxRequest, app: Container = Depends(get_container)) -> Dict[str, Any]:
    """A box drawn on a rendered view → the 3D box of the nearest scan surface behind it."""
    with http_errors():
        return app.placements.lift(body.view_projection, body.image_box)


def list_placements(app: Container = Depends(get_container)) -> Dict[str, Dict[str, Any]]:
    """Operator-confirmed boxes keyed by asset id."""
    return app.placements.all()


def save_placement(asset_id: str, body: PlacementBox, app: Container = Depends(get_container)) -> Dict[str, Any]:
    with http_errors():
        return app.placements.save(asset_id, body.center, body.size, body.status)


def delete_placement(asset_id: str, app: Container = Depends(get_container)) -> Dict[str, str]:
    app.placements.delete(asset_id)
    return {"status": "deleted"}
