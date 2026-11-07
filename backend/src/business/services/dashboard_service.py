"""Plant-wide health KPIs."""

from typing import Any, Dict

from business.interfaces.ports.outbound import AssetRepository


class DashboardService:
    def __init__(self, assets: AssetRepository):
        self._assets = assets

    def summary(self) -> Dict[str, Any]:
        states = list(self._assets.states().values())
        counts = self._assets.counts()
        average = sum(s["health_score"] for s in states) / len(states) if states else 0.0
        condition_counts = {"healthy": 0, "watch": 0, "degraded": 0, "attention_required": 0}
        for state in states:
            key = state["condition_state"].lower()
            condition_counts[key] = condition_counts.get(key, 0) + 1
        return {
            "total_assets": counts["assets"],
            "average_health_score": round(average, 1),
            "condition_counts": condition_counts,
            "healthy_count": condition_counts.get("healthy", 0),
            "watch_count": condition_counts.get("watch", 0),
            "degraded_count": condition_counts.get("degraded", 0),
            "attention_required_count": condition_counts.get("attention_required", 0),
            "total_telemetry_samples": counts["telemetry"],
            "total_alarms_events": counts["events"],
            "high_severity_events": counts["high_events"],
            "total_maintenance_records": counts["work_orders"],
            "total_data_quality_issues": counts["data_quality"],
        }
