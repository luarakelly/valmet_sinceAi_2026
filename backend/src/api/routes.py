"""Every REST endpoint in one place: path + method -> controller. No logic here.

Mounted at /api by api/server.py. Paths follow the builder pack's API_Contract plus scene,
navigation, copilot and vision endpoints used by the frontend.
"""

from typing import List

from fastapi import APIRouter, status

from api.controllers import (
    asset_controller as assets,
    copilot_controller as copilot,
    dashboard_controller as dashboard,
    maintenance_controller as maintenance,
    navigation_controller as navigation,
    placement_controller as placements,
    scene_controller as scene,
    verification_controller as verification,
    vision_controller as vision,
    work_order_controller as work_orders,
)
from dto.asset_dto import (
    AlarmEventRead,
    AssetDetailRead,
    AssetRead,
    KnowledgeDocRead,
    MaintenanceHistoryRead,
    SceneAnchorRead,
    TelemetryRead,
)
from dto.copilot_dto import CopilotQueryResponse
from dto.dashboard_dto import DashboardSummaryResponse
from dto.maintenance_dto import MaintenancePriorityRead
from dto.navigation_dto import NavigationPathResponse, WalkableGridResponse
from dto.placement_dto import LiftBoxResponse
from dto.scene_dto import ProximityAssetResponse
from dto.vision_dto import VisionAnalysisResponse
from dto.work_order_dto import WorkOrderDraftResponse

router = APIRouter(tags=["Ask Your Factory"])
get, post, put, delete = router.get, router.post, router.put, router.delete

# Assets & evidence (API_Contract)
get("/assets", response_model=List[AssetRead])(assets.list_assets)
get("/assets/{id}", response_model=AssetDetailRead)(assets.get_asset_detail)
get("/assets/{id}/telemetry", response_model=List[TelemetryRead])(assets.get_asset_telemetry)
get("/assets/{id}/events", response_model=List[AlarmEventRead])(assets.get_asset_events)
get("/assets/{id}/documents", response_model=List[KnowledgeDocRead])(assets.get_asset_documents)
get("/assets/{id}/work-orders", response_model=List[MaintenanceHistoryRead])(assets.get_asset_work_orders)

# Scene
get("/scene/frames")(scene.get_scene_frames)
get("/scene/summary")(scene.get_scene_summary)
get("/scene/anchors", response_model=List[SceneAnchorRead])(scene.get_scene_anchors)
post("/scene/proximity", response_model=List[ProximityAssetResponse])(scene.query_proximity)
post("/scene/extract-assets")(scene.extract_scene_assets)
get("/scene/boiler-room.ply")(scene.get_boiler_room_ply)
get("/scene/boiler-room-mesh.ply")(scene.get_boiler_room_mesh)
get("/scene/boiler-room.splat")(scene.get_boiler_room_splat)
get("/scene/objects/{id}/geometry")(scene.get_object_geometry)
post("/scene/objects/{id}/verification")(verification.verify_object)
get("/scene/verification")(verification.list_verification)
post("/scene/verification/reset")(verification.reset_verification)
post("/scene/lift-box", response_model=LiftBoxResponse)(placements.lift_box)
get("/scene/placements")(placements.list_placements)
put("/scene/placements/{asset_id}")(placements.save_placement)
delete("/scene/placements/{asset_id}")(placements.delete_placement)

# Navigation
get("/navigation/path", response_model=NavigationPathResponse)(navigation.get_navigation_path)
get("/navigation/walkable", response_model=WalkableGridResponse)(navigation.get_walkable_grid)

# AI & workflow
post("/copilot/query", response_model=CopilotQueryResponse)(copilot.copilot_query)
post("/work-orders/draft", response_model=WorkOrderDraftResponse, status_code=status.HTTP_201_CREATED)(work_orders.create_draft_work_order)
get("/maintenance/priorities", response_model=List[MaintenancePriorityRead])(maintenance.get_maintenance_priorities)
get("/metaverse/dashboard", response_model=DashboardSummaryResponse)(dashboard.get_metaverse_dashboard)
post("/vision/analyze", response_model=VisionAnalysisResponse)(vision.analyze_viewport_view)
