from typing import Any, Dict

from fastapi import Depends

from api.container import Container, get_container
from api.controllers.errors import http_errors
from dto.labeling_dto import ViewUpload


def get_plan(app: Container = Depends(get_container)) -> Dict[str, Any]:
    """Camera poses to render for the labeling run, and which views already exist."""
    return app.labeling.plan()


def save_view(body: ViewUpload, app: Container = Depends(get_container)) -> Dict[str, Any]:
    with http_errors():
        return app.labeling.save_view(body.view_id, body.image_base64, body.view_projection, body.width, body.height)
