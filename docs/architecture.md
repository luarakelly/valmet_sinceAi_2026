# Architecture (hexagonal)

```text
frontend/ (Three.js)  ──HTTP──►  api/  (driving adapter)
                                   routes.py        one light table: path → controller
                                   controllers/     call a use case, map to a DTO, errors → HTTP
                                   container.py     composition root (wires adapters into services)
                                   server.py        FastAPI app, static frontend, startup
                                 dto/               request/response contracts (what the frontend reads)
                                 business/          use cases — no FastAPI, SQLModel, NumPy or HTTP
                                   services/        asset, scene, navigation, copilot, work order,
                                                    dashboard, maintenance, vision
                                   interfaces/ports inbound (use cases) / outbound (what infra provides)
                                   errors.py        NotFound, RouteNotFound, … (mapped to 404, 409, …)
                                 infra/             driven adapters
                                   db/sqlmodel/     tables, engine + seeding, SqlModelAssetRepository
                                   importers/       builder pack loader (Excel or JSON cache)
                                   spatial/         PLY → canonical cloud → segmentation → mapping → grid/A*
                                   llm/             Gemini and Claude adapters (optional)
                                   vision/          YOLO-World adapter (optional, lazy)
```

## Dependency rule

`api → business ← infra`. Business code depends only on its ports. Controllers depend on
services and DTOs. Only `api/container.py` knows which adapter implements which port.

## Outbound ports

| Port | Adapter | Notes |
|---|---|---|
| `AssetRepository` | `infra/db/sqlmodel/repositories/asset_repository.py` | Returns plain records (builder-pack field names). |
| `SceneEngine` | `infra/spatial/scene_pipeline.py` (`BoilerRoomScene`) | Built once at startup (~1 s); assets injected by the container. |
| `LanguageModel` | `infra/llm/gemini_language_model.py`, `claude_language_model.py` | `LLM_PROVIDER=gemini|claude|none`; answers kept only if every cited ID is real evidence. |
| `VisualDetector` | `infra/vision/yolo_world_detector.py` | Weights in `data/weights/` or downloaded by ultralytics. |

## Coordinates

Canonical scene frame: metres, **Y up, floor at y = 0**, room centred on x = z = 0. The viewer
PLY, the mesh, every frame (`pos`, `size`) and every route waypoint use this frame.

## Guarantees

- Routes are re-measured on the final segments; `collision_free` and `min_clearance_m` are reported, and "no route" is an HTTP 409, never a fake path.
- Asset ↔ object mapping is synthetic (allowed by the brief) and carries a `mapping_confidence`.
- Diagnoses cite only builder-pack IDs; LLM answers that cite anything else are discarded.
- Work orders are drafts; nothing triggers a physical action.
