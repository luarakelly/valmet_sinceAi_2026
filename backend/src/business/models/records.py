"""Domain records exchanged across ports.

Repositories return plain mappings with the builder-pack field names (asset_id, tag,
asset_class, health_score, ...), so business code never depends on SQLModel tables and the
contracts match the workbook. Typed aliases document intent.
"""

from typing import Any, Dict

AssetRecord = Dict[str, Any]          # Asset_Master row
StateRecord = Dict[str, Any]          # Current_State row
TelemetryRecord = Dict[str, Any]      # Telemetry_Sample_3d row
EventRecord = Dict[str, Any]          # Alarms_Events row
WorkOrderRecord = Dict[str, Any]      # Maintenance_History row
DocumentRecord = Dict[str, Any]       # Knowledge_Docs row
ServiceCaseRecord = Dict[str, Any]    # Historical_Service_Cases row
DataQualityRecord = Dict[str, Any]    # Data_Quality row
SceneFrame = Dict[str, Any]           # extracted object frame (pos, size, label, mapped asset)
