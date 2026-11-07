# Challenge alignment and requirement traceability

Sources: *Valmet x SinceAI 2026 Challenge Brief*, builder-pack `Builder_Questions`
and `API_Contract` sheets.

## Minimum demo requirements (brief §7)

| Requirement | Where |
|---|---|
| Process `Industrial Boiler Room.ply`, extract and 3D-frame many objects | `infra/spatial/` (point_cloud → segmentation), `GET /api/scene/frames` (144 frames) |
| Map Excel statuses/telemetry/metadata, procedural mapping, faulty target | `infra/importers/workbook/dataset.py` → SQLModel; `infra/spatial/asset_mapping.py` (30/30 bound, spread out); target = lowest health (P-005) |
| Robot walks a logical, collision-free path to the faulty device | `infra/spatial/navigation.py` (inflated grid, A*, measured clearance), `GET /api/navigation/path` |
| Highlight nearby frames + metadata while walking | Frontend proximity (1.5 m) + `POST /api/scene/proximity` |
| AI diagnosis and service guidance at the target | `business/services/copilot_service.py` (drift, alarms, cases, docs, data-quality penalty) + Gemini/Claude with citation check, `POST /api/copilot/query` |
| Convenient UI | `frontend/` guided flow (scene → walk → diagnosis) |

## Builder questions

| ID | Status |
|---|---|
| Q-01 3D device → state, evidence, docs | `GET /api/assets/{id}`, click a frame in the viewer |
| Q-02 Multivariate degradation | `detect_drift` (Welch t-score vs own baseline) |
| Q-03 Evidence IDs + confidence | `evidence_citations`, `confidence_score` in every diagnosis |
| Q-04 Prioritise by condition, criticality, uncertainty | `GET /api/maintenance/priorities` |
| Q-05 3D object → evidence → case → work-order draft | asset detail → copilot → `POST /api/work-orders/draft` |
| Q-06 Lower confidence for poor data/mapping | data-quality penalty + mapping confidence factor |
| Q-07 Swap synthetic feeds for OPC UA/MQTT | new `AssetRepository` adapter; services unchanged |
| Q-08 Upgrade mapping to CV/VLM | new `SceneEngine` adapter; YOLO-World already behind `VisualDetector` |
| Q-09 Portable across 3D stacks | JSON frames in a documented Y-up frame |
| Q-10 Evidence package for remote experts | diagnosis JSON + citations + draft work order |

## Out of scope

MQTT/live IoT, authentication, mobile app, physical control. All AI output is advisory.
