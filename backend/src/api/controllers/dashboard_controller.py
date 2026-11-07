from fastapi import Depends

from api.container import Container, get_container
from dto.dashboard_dto import DashboardSummaryResponse


def get_metaverse_dashboard(app: Container = Depends(get_container)) -> DashboardSummaryResponse:
    """Plant-wide health, condition counts and data-quality metrics."""
    return DashboardSummaryResponse.model_validate(app.dashboard.summary())
