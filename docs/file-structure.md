# File structure

```text
valmet_sinceAi_2026/
├── backend/
│   ├── src/
│   │   ├── main.py                         # python backend/src/main.py → uvicorn api.server:app
│   │   ├── api/                            # driving adapter (HTTP)
│   │   │   ├── server.py                   # FastAPI app, startup, static frontend at /
│   │   │   ├── container.py                # composition root
│   │   │   ├── routes.py                   # all /api endpoints → controllers
│   │   │   └── controllers/                # asset, scene, navigation, copilot, work_order,
│   │   │                                   # dashboard, maintenance, vision, health, errors
│   │   ├── dto/                            # API contracts (Pydantic)
│   │   │   ├── asset_dto.py  scene_dto.py  navigation_dto.py  copilot_dto.py
│   │   │   └── work_order_dto.py  dashboard_dto.py  maintenance_dto.py
│   │   ├── business/
│   │   │   ├── errors.py
│   │   │   ├── models/records.py           # record types exchanged across ports
│   │   │   ├── interfaces/ports/{inbound,outbound}/
│   │   │   └── services/                   # asset, scene, navigation, copilot (+ drift),
│   │   │                                   # work_order, dashboard, maintenance, vision
│   │   └── infra/
│   │       ├── paths.py                    # repo / data / frontend locations
│   │       ├── db/sqlmodel/                # tables.py, database.py (engine + seed), repositories/
│   │       ├── importers/workbook/dataset.py
│   │       ├── spatial/                    # point_cloud, segmentation, navigation,
│   │       │                               # asset_mapping, splat_mesh, scene_pipeline
│   │       ├── llm/                        # gemini, claude, build_language_model()
│   │       └── vision/yolo_world_detector.py
│   ├── tests/
│   │   ├── unit/business/                  # services with in-memory fakes
│   │   ├── unit/infra/spatial/             # extraction density, canonical frame, routes
│   │   └── integration/api/                # HTTP contract + end-to-end acceptance
│   ├── conftest.py   requirements.txt
├── frontend/                               # index.html, src/js/app.js, src/styles/app.css
├── data/                                   # viewer PLY + mesh (tracked), workbook, cache;
│   ├── input/                              #   raw 355 MB splat (ignored)
│   └── weights/                            #   YOLO weights (ignored, auto-download)
├── scripts/                                # build_mesh.py, seed_database.py
├── docs/
├── initialize.sh/.bat   run.sh/.bat
└── README.md
```
