"""Plant dashboard contract."""

from typing import Dict

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    """Overall plant metaverse operational health summary."""
    total_assets: int = 30
    average_health_score: float = 81.2
    condition_counts: Dict[str, int] = {}
    healthy_count: int = 17
    watch_count: int = 4
    degraded_count: int = 6
    attention_required_count: int = 3
    total_telemetry_samples: int = 4320
    total_alarms_events: int = 1000
    active_alarms_count: int = 512
    high_severity_events: int = 153
    total_maintenance_records: int = 300
    open_work_orders_count: int = 42
    total_data_quality_issues: int = 120
    data_quality_issues_count: int = 120
