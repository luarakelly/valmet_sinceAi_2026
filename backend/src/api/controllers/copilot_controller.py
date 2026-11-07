from fastapi import Depends

from api.container import Container, get_container
from api.controllers.errors import http_errors
from dto.copilot_dto import CopilotQueryRequest, CopilotQueryResponse


def copilot_query(request: CopilotQueryRequest, app: Container = Depends(get_container)) -> CopilotQueryResponse:
    """Evidence-grounded diagnosis: telemetry drift, alarms, similar cases, docs and data quality."""
    with http_errors():
        result = app.copilot.diagnose(request.asset_id, request.prompt or request.query)
    return CopilotQueryResponse.model_validate(result)
