"""Composition root: the only module that knows every adapter.

Built once per process (startup) and shared by the controllers.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session

from business.services import (
    AssetService,
    CopilotService,
    DashboardService,
    MaintenanceService,
    NavigationService,
    SceneService,
    VisionService,
    WorkOrderService,
)
from infra.db.sqlmodel.database import engine, init_db
from infra.db.sqlmodel.repositories import SqlModelAssetRepository
from infra.importers.workbook.dataset import get_dataset
from infra.llm import build_language_model
from infra.spatial.scene_pipeline import BoilerRoomScene
from infra.vision.yolo_world_detector import YoloWorldDetector

logger = logging.getLogger("ask_your_factory.container")


@dataclass
class Container:
    assets: AssetService
    scene: SceneService
    navigation: NavigationService
    copilot: CopilotService
    work_orders: WorkOrderService
    dashboard: DashboardService
    maintenance: MaintenanceService
    vision: VisionService
    llm_name: Optional[str]


_container: Optional[Container] = None


def build_container(populate_db: bool = True) -> Container:
    init_db(populate=populate_db)
    repository = SqlModelAssetRepository(lambda: Session(engine))
    scene_engine = BoilerRoomScene(get_dataset().get_assets)
    llm = build_language_model()
    scene = SceneService(scene_engine, repository)
    assets = AssetService(repository, scene)
    container = Container(
        assets=assets,
        scene=scene,
        navigation=NavigationService(scene_engine),
        copilot=CopilotService(repository, scene_engine, llm),
        work_orders=WorkOrderService(repository, assets),
        dashboard=DashboardService(repository),
        maintenance=MaintenanceService(repository, scene),
        vision=VisionService(YoloWorldDetector()),
        llm_name=llm.name if llm else None,
    )
    logger.info("Container ready (LLM: %s)", container.llm_name or "none, deterministic evidence engine")
    return container


def get_container() -> Container:
    """FastAPI dependency / accessor. Builds lazily so tests and scripts work without lifespan."""
    global _container
    if _container is None:
        _container = build_container()
    return _container
