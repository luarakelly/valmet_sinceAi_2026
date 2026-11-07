from fastapi import Depends

from api.container import Container, get_container
from api.controllers.errors import http_errors
from dto.work_order_dto import WorkOrderDraftRequest, WorkOrderDraftResponse


def create_draft_work_order(payload: WorkOrderDraftRequest, app: Container = Depends(get_container)) -> WorkOrderDraftResponse:
    """Draft work order grounded in DOC-FIELD-SAFETY. Does NOT execute any control action."""
    with http_errors():
        return WorkOrderDraftResponse.model_validate(app.work_orders.draft(payload.model_dump()))
