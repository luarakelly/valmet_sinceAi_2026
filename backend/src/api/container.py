"""Composition root: the only module that knows every adapter.

Built once per process (startup) and shared by the controllers.
"""

import logging
import threading
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
    VerificationService,
    VisionService,
    WorkOrderService,
)
from infra.db.sqlmodel.database import engine, init_db
from infra.db.sqlmodel.repositories import SqlModelAssetRepository
from infra.importers.workbook.dataset import get_dataset
from infra.llm import build_language_model
from infra.spatial.scene_pipeline import BoilerRoomScene
from infra.spatial.verification_store import JsonVerificationStore
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
    verification: VerificationService
    llm_name: Optional[str]


_container: Optional[Container] = None
_container_lock = threading.Lock()


def build_container(populate_db: bool = True) -> Container:
    init_db(populate=populate_db)
    repository = SqlModelAssetRepository(lambda: Session(engine))
    verification_store = JsonVerificationStore()
    scene_engine = BoilerRoomScene(get_dataset().get_assets, verification_store.all)
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
        verification=VerificationService(scene, llm, verification_store),
        llm_name=llm.name if llm else None,
    )
    logger.info("Container ready (LLM: %s)", container.llm_name or "none, deterministic evidence engine")
    return container


def get_container() -> Container:
    """FastAPI dependency / accessor. Builds lazily so tests and scripts work without lifespan."""
    global _container
    # Lock so concurrent first requests share one build instead of each starting a full pipeline.
    with _container_lock:
        if _container is None:
            _container = build_container()
    return _container
