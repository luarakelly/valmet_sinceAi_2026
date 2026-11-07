# Semantic 3D Labeling (RGB-D + Grounded-SAM 2 + Back-projection + DBSCAN) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically label and box every piece of equipment in the Equipment Room splat, replacing the wrong provided boxes, and feed the result into the simulator.

**Architecture:** An offline batch, not a request path. (1) The viewer renders 20–50 photoreal views from virtual cameras on walkable cells and uploads image + exact `view_projection`. (2) `scripts/label_scene.py` runs GroundingDINO + SAM 2 per view (masks cached), z-buffers the Gaussian centres with the same matrix, keeps points inside each mask within ±15 cm of the visible surface, accumulates per-point label votes across views, runs DBSCAN per label, fits gravity-aligned oriented boxes and writes `data/semantic_objects.json`. (3) The scene pipeline loads that file at startup: semantic objects replace the geometric ones they cover, bind pack assets by meaning, and render as rotated frames.

**Tech Stack:** Python 3.14, NumPy, SciPy, scikit-learn (DBSCAN), transformers (GroundingDINO), ultralytics (SAM 2.1), CUDA torch; FastAPI; Three.js + Spark.

**Spec:** `docs/superpowers/specs/2026-11-07-semantic-3d-labeling.md`

## Global Constraints

- Thresholds from the spec, as named constants: `VISIBLE_DEPTH_TOLERANCE_M = 0.15`, `DBSCAN_EPS_M = 0.10`, `DBSCAN_MIN_SAMPLES = 30`, view count 20–50 (`VIEW_COUNT = 40`).
- Prompt list must include the spec's `crate, pipe, valve, fire extinguisher, pallet, hazard` (sent to GroundingDINO as `"hazard sign"`).
- Coordinates: canonical scene frame (metres, Y up, floor y = 0). Matrices: three.js `Matrix4.elements`, column-major, `view_projection = projectionMatrix × matrixWorldInverse`, image origin top-left.
- Dependencies: add only `transformers` and `scikit-learn` to `backend/requirements.txt`. No open3d (numpy/scipy cover box fitting).
- Heavy models never run inside the FastAPI process; the server only reads `data/semantic_objects.json` and must start normally without it.
- Code style (team standard): no ternaries, no one-line `if`/`for`, no magic numbers, no globals, functions fit one screen, boolean names are predicates, domain names over `data`/`info`/`helper`.
- Tests: `cd backend && .venv/bin/python -m pytest -q` (Windows: `.venv/Scripts/python`). GPU-only tests carry `@pytest.mark.gpu` and are skipped when `torch.cuda.is_available()` is false.
- Commit after every task on branch `veikka`; author Veikka Liukkonen.

## Review Focus

1. A mask covering a wall or the floor ("pipe" over half the image) must not label the room: drop masks above `MAX_MASK_FRACTION = 0.35` of the image (test in Task 4).
2. A splat floater or a one-off false detection must not create an object: a point needs votes from `MIN_VIEWS = 2` distinct views (test in Task 5).
3. The same object called "valve" in one view and "pipe" in another must get one label, the majority by score (test in Task 5).
4. A thin pipe in front of a wall must select the pipe, not the wall behind it (±15 cm visibility test in Task 3).
5. Missing GPU, missing model weights or an empty views folder: the CLI exits with a one-line reason and non-zero code, and the server keeps working with geometric objects when `data/semantic_objects.json` is absent or malformed (tests in Tasks 7 and 8).

## File Structure

| File | Responsibility |
|---|---|
| `backend/src/infra/labeling/vocabulary.py` | Prompt → label → pack asset class table |
| `backend/src/infra/labeling/camera_rig.py` | Virtual camera poses on walkable cells |
| `backend/src/infra/labeling/view_store.py` | Captured views on disk: `data/labeling/views/<id>.jpg` + `<id>.json` |
| `backend/src/infra/labeling/backprojection.py` | Projection, z-buffer visibility, points inside a mask |
| `backend/src/infra/labeling/segmenter.py` | GroundingDINO + SAM 2 adapter (lazy, GPU) |
| `backend/src/infra/labeling/fusion.py` | Per-point multi-view label votes and assignment |
| `backend/src/infra/labeling/instances.py` | DBSCAN instances + gravity-aligned oriented box fit |
| `backend/src/infra/labeling/semantic_objects.py` | JSON schema read/write → `SceneObject`s |
| `backend/src/business/services/labeling_service.py` + `api/controllers/labeling_controller.py` + `dto/labeling_dto.py` | Views endpoints for the capture run |
| `scripts/label_scene.py` | Batch CLI: segment → back-project → fuse → cluster → write JSON |
| `scripts/eval_labels.py` | IoU/label metrics against ground truth and baselines |
| `frontend/src/js/authoring.js` | "Capture labeling views" and "Save as ground truth" |
| `infra/spatial/segmentation.py`, `scene_pipeline.py`, `asset_mapping.py`, `frontend/src/js/app.js` | Yaw on objects, merge semantic objects, bind by meaning, draw rotated frames |

---

### Task 0: Go/no-go spike — does Grounded-SAM 2 see equipment in our renders? (≈20 min, no commit)

The riskiest assumption: YOLO-World found nothing on earlier renders. Prove detection works before building.

- [ ] **Step 1: Check the GPU and install the two dependencies**

Run: `backend/.venv/bin/python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"` then `backend/.venv/bin/python -m pip install "transformers>=4.56" "scikit-learn>=1.7"`.
Expected: `True <GPU name>`; both packages install. If `False`, note it: GroundingDINO-tiny and SAM 2.1-small still run on CPU at roughly 5–15 s per view.

- [ ] **Step 2: Capture 5 views by hand**

Open `http://localhost:8000/?author`, fly close to equipment (Shift+F), and save 5 canvas captures (`renderer.domElement.toBlob`) to `data/labeling/spike/`.

- [ ] **Step 3: Run GroundingDINO + SAM 2 on them in a throwaway script**

Use `IDEA-Research/grounding-dino-base` (`AutoModelForZeroShotObjectDetection`, `box_threshold=0.30`, `text_threshold=0.25`, prompt `"crate . pallet . pipe . valve . handwheel . pump . electric motor . pressure gauge . fire extinguisher . electrical cabinet . tank . hazard sign ."`) and `ultralytics.SAM("sam2.1_b.pt")` with the boxes as prompts. Save overlay PNGs.

- [ ] **Step 4: Decide**

GO if at least 3 of 5 views have at least one correct, tight detection. Then edit the vocabulary from what is actually in the room (Task 1 table). NO-GO: switch the segmenter in Task 4 to "geometric instances + CLIP labels" (`openai/clip-vit-large-patch14` scoring crops of the existing 533 objects projected into the views). Tasks 1–3 and 5–9 are unchanged.

### Task 1: Vocabulary and camera rig (≈25 min)

**Files:**
- Create: `backend/src/infra/labeling/__init__.py`, `vocabulary.py`, `camera_rig.py`
- Test: `backend/tests/unit/infra/labeling/test_camera_rig.py`

**Interfaces:**
- Produces: `VOCABULARY: Tuple[Term, ...]` where `Term(prompt: str, label: str, asset_class: Optional[str])`; labels are UPPER_SNAKE (`CRATE`, `PALLET`, `PIPE`, `VALVE`, `HANDWHEEL`, `PUMP`, `ELECTRIC_MOTOR`, `PRESSURE_GAUGE`, `FIRE_EXTINGUISHER`, `ELECTRICAL_CABINET`, `TANK`, `HAZARD_SIGN`); asset classes: `VALVE`/`HANDWHEEL`→`CONTROL_VALVE`, `PUMP`→`PROCESS_PUMP`, `ELECTRIC_MOTOR`→`ELECTRIC_MOTOR`, `PRESSURE_GAUGE`→`PRESSURE_TRANSMITTER`, others `None`.
- Produces: `CameraView(view_id: str, eye: Tuple[float,float,float], target: Tuple[float,float,float], fov_deg: float)` and `plan_views(grid: OccupancyGrid, count: int = VIEW_COUNT) -> List[CameraView]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_views_stand_on_reachable_floor_at_eye_height():
    grid = open_room_grid()
    views = plan_views(grid, count=40)
    assert 20 <= len(views) <= 50
    for view in views:
        assert grid.is_reachable(view.eye[0], view.eye[2])
        assert view.eye[1] == EYE_HEIGHT_M

def test_views_look_outward_in_several_directions():
    views = plan_views(open_room_grid(), count=40)
    yaws = {round(math.degrees(math.atan2(v.target[0]-v.eye[0], v.target[2]-v.eye[2]))) % 360 for v in views}
    assert len(yaws) >= YAWS_PER_STATION

def test_plan_is_deterministic_and_ids_unique():
    assert plan_views(open_room_grid()) == plan_views(open_room_grid())
    assert len({v.view_id for v in plan_views(open_room_grid())}) == len(plan_views(open_room_grid()))
```

- [ ] **Step 2: Run, expect FAIL** — `pytest tests/unit/infra/labeling/test_camera_rig.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Stations: farthest-point sampling over reachable cells (seeded at the cell nearest the room centre), `STATIONS = 8`. At each, `YAWS_PER_STATION = 5` yaws spaced 72°, offset by station index × 36° so stations don't share directions. `EYE_HEIGHT_M = 1.6`, `PITCH_DEG = -15`, `FOV_DEG = 70`, target 2 m along the look direction. `view_id = f"V{station:02d}-{yaw_index}"`. Use `navigation.OccupancyGrid` (reachable mask, `to_world`); add `is_reachable` only if it doesn't exist.

- [ ] **Step 4: Run, expect PASS.** — [ ] **Step 5: Commit** `feat(labeling): vocabulary and virtual camera rig`

### Task 2: Capture views from the photoreal viewer (≈35 min)

**Files:**
- Create: `backend/src/infra/labeling/view_store.py`, `backend/src/business/services/labeling_service.py`, `backend/src/dto/labeling_dto.py`, `backend/src/api/controllers/labeling_controller.py`
- Modify: `backend/src/api/routes.py`, `backend/src/api/container.py`, `backend/src/infra/paths.py` (`LABELING_DIR = DATA_DIR / "labeling"`), `frontend/src/js/authoring.js`, `.gitignore` (`data/labeling/views/`)
- Test: `backend/tests/unit/infra/labeling/test_view_store.py`

**Interfaces:**
- Consumes: `plan_views`, `CameraView` (Task 1).
- Produces: `ViewStore(root: Path)` with `save(view_id: str, image: bytes, view_projection: List[float], width: int, height: int) -> None`, `views() -> List[CapturedView]`, `CapturedView(view_id, image_path: Path, view_projection: np.ndarray (16,), width: int, height: int)`.
- Produces endpoints: `GET /api/labeling/views` → `[{view_id, eye, target, fov_deg}]`; `PUT /api/labeling/views/{view_id}` multipart (`file`, `view_projection` JSON string of 16 floats, `width`, `height`) → `{"view_id", "saved": true}`; 404 for a `view_id` not in the plan; 400 for a malformed matrix.

- [ ] **Step 1: Write the failing tests**

```python
def test_saved_view_round_trips(tmp_path):
    store = ViewStore(tmp_path)
    store.save("V00-0", JPEG_BYTES, IDENTITY_16, 1280, 720)
    [view] = store.views()
    assert view.view_id == "V00-0" and view.width == 1280 and view.view_projection.shape == (16,)

def test_resaving_a_view_replaces_it(tmp_path): ...  # two saves → one view, latest matrix

def test_a_view_without_its_image_is_skipped(tmp_path): ...  # json alone → views() == []
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement the store, service (`LabelingService.planned_views()`, `save_view(...)` validating the id against the plan), DTO, controller and routes.** Writes are atomic (`.tmp` then `replace`), as `JsonRecordStore` does.
- [ ] **Step 4: Frontend.** In `authoring.js`, add a "Capture labeling views" button. For each planned view: `setCameraMode("free")`, set `camera.position` to `eye`, `camera.fov` to `fov_deg` (then `updateProjectionMatrix`), `controls.target` to `target` (then `controls.update()`). Wait 2 animation frames plus `SPLAT_SETTLE_MS = 400` so Spark can sort. Capture with the existing `captureSceneImage()` (overlays hidden), compute `currentViewProjection()`, and PUT it with the canvas `width`/`height`. Show "n / total" in the status line, and restore the camera at the end.
- [ ] **Step 5: Verify live.** Click the button and expect 40 `.jpg` + `.json` pairs in `data/labeling/views/`. Open 3 images and check they show the room with no robot, path or frames.
- [ ] **Step 6: Run tests, expect PASS; commit** `feat(labeling): capture photoreal views with exact camera matrices`

### Task 3: Back-projection with visible-surface test (≈30 min)

**Files:** Create `backend/src/infra/labeling/backprojection.py`; Test `backend/tests/unit/infra/labeling/test_backprojection.py`

**Interfaces:**
- Produces: `Projection(px: np.ndarray[int], py: np.ndarray[int], depth: np.ndarray[float], is_in_view: np.ndarray[bool])`
- `project(xyz: np.ndarray, view_projection: np.ndarray, width: int, height: int) -> Projection`
- `visible_points(projection: Projection, width: int, height: int) -> np.ndarray[bool]`
- `points_in_mask(projection: Projection, is_visible: np.ndarray, mask: np.ndarray[bool, (height, width)]) -> np.ndarray[int]` (point indices)

- [ ] **Step 1: Write the failing tests** (reuse the perspective-matrix fixture from `tests/unit/infra/spatial/test_placements.py`, moved to `tests/unit/conftest.py` as `camera_at_origin_looking_down_minus_z`)

```python
def test_mask_over_a_pipe_selects_the_pipe_not_the_wall_behind():
    xyz = np.vstack([pipe_at_depth(5.0), wall_at_depth(5.5)])        # wall only 0.5 m behind
    projection = project(xyz, VIEW_PROJECTION, 640, 480)
    picked = points_in_mask(projection, visible_points(projection, 640, 480), centre_mask(640, 480))
    assert set(picked) <= set(range(PIPE_POINTS))
    assert len(picked) > 0.5 * PIPE_POINTS

def test_points_behind_the_camera_or_outside_the_image_are_never_picked(): ...

def test_surface_within_15_cm_counts_as_visible():
    # two layers 0.10 m apart on the same pixels: both visible; 0.30 m apart: only the front one
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Projection matches `infra/spatial/placements.py::_points_in_view_box` (reuse it by extracting a shared `project_to_image()` there, so the math lives in one place). Visibility is a z-buffer on `DEPTH_CELL_PX = 4` pixel cells:

```python
cell = (py // DEPTH_CELL_PX) * cells_wide + (px // DEPTH_CELL_PX)
nearest = np.full(cell_count, np.inf); np.minimum.at(nearest, cell[in_view], depth[in_view])
is_visible = in_view & (depth <= nearest[cell] + VISIBLE_DEPTH_TOLERANCE_M)
```

- [ ] **Step 4: Run, expect PASS; commit** `feat(labeling): back-project masks onto visible Gaussians`

### Task 4: Grounded-SAM 2 segmenter (≈30 min)

**Files:** Create `backend/src/infra/labeling/segmenter.py`; Modify `backend/requirements.txt` (`transformers>=4.56`, `scikit-learn>=1.7`); Test `backend/tests/unit/infra/labeling/test_segmenter.py`

**Interfaces:**
- Produces: `MaskDetection(label: str, score: float, mask: np.ndarray[bool, (h, w)])`
- `GroundedSam2Segmenter(device: str = "auto")` (`auto` = CUDA when `torch.cuda.is_available()`, else CPU, logged once) with `segment(image: np.ndarray[uint8, (h, w, 3)]) -> List[MaskDetection]`. Models load lazily on first call. Labels come from `VOCABULARY` (prompt → label).
- `keep_plausible(detections: List[MaskDetection], image_area: int) -> List[MaskDetection]`: a pure filter.

- [ ] **Step 1: Write the failing tests**

```python
def test_masks_covering_more_than_35_percent_of_the_image_are_dropped():
    big, small = detection(area_fraction=0.5), detection(area_fraction=0.05)
    assert keep_plausible([big, small], IMAGE_AREA) == [small]

def test_unknown_prompts_are_dropped(): ...      # a phrase not in VOCABULARY → removed

@pytest.mark.gpu
def test_finds_something_in_a_captured_view():
    image = load_first_captured_view()            # skip if data/labeling/views is empty
    assert len(GroundedSam2Segmenter().segment(image)) >= 1
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** GroundingDINO (`IDEA-Research/grounding-dino-base`, `BOX_THRESHOLD = 0.30`, `TEXT_THRESHOLD = 0.25`) gives boxes. Map each phrase to the first `Term` whose prompt it contains; SAM 2 (`ultralytics.SAM("sam2.1_b.pt")`, box prompts) gives one mask per box; `MAX_MASK_FRACTION = 0.35`. If Task 0 was NO-GO, implement the CLIP-crop variant behind the same `segment()` signature.
- [ ] **Step 4: Run, expect PASS (GPU test may skip); commit** `feat(labeling): GroundingDINO + SAM 2 segmenter`

### Task 5: Multi-view label fusion (≈25 min)

**Files:** Create `backend/src/infra/labeling/fusion.py`; Test `backend/tests/unit/infra/labeling/test_fusion.py`

**Interfaces:**
- Produces: `LabelVotes(point_count: int, labels: Tuple[str, ...])` with `add(view_id: str, label: str, score: float, point_indices: np.ndarray) -> None`, `mark_seen(point_indices: np.ndarray) -> None` and `assign() -> np.ndarray[int]` (index into `labels`, `-1` = unlabeled).
- Rule: a point takes the label with the highest score sum, only if (a) that label came from at least `MIN_VIEWS = 2` distinct views, and (b) `score_sum / times_seen ≥ MIN_LABEL_SHARE = 0.3`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_label_seen_in_two_views_sticks(): ...                  # crate in V1 and V2 → CRATE
def test_a_label_from_a_single_view_is_ignored(): ...             # crate only in V1 → -1
def test_conflicting_labels_resolve_to_the_higher_score_sum(): ...  # valve .8+.7 vs pipe .6 → VALVE
def test_a_point_seen_often_but_rarely_labeled_stays_unlabeled(): ... # seen 10×, labeled 2× at .5 → -1
```

- [ ] **Step 2: Run, expect FAIL.** — [ ] **Step 3: Implement** (`float32` score sums and `int16` distinct-view counts, both `(point_count, len(labels))`; `add()` deduplicates indices with `np.unique` so one view adds at most 1 to a point's view count; `int32` `times_seen` from `mark_seen`). — [ ] **Step 4: PASS; commit** `feat(labeling): multi-view label voting`

### Task 6: DBSCAN instances and oriented boxes (≈30 min)

**Files:** Create `backend/src/infra/labeling/instances.py`; Test `backend/tests/unit/infra/labeling/test_instances.py`

**Interfaces:**
- Produces: `OrientedBox(center: Tuple[float,float,float], size: Tuple[float,float,float], yaw: float)`, where `size = (width along local x, height, depth along local z)`, yaw is in radians about +Y, and the box is gravity-aligned.
- `Instance(label: str, points: np.ndarray, box: OrientedBox)`
- `cluster_instances(xyz: np.ndarray, assigned: np.ndarray[int], labels: Tuple[str, ...]) -> List[Instance]`
- `fit_box(points: np.ndarray) -> OrientedBox`
- `box_iou(a: OrientedBox, b: OrientedBox) -> float`: intersection of the two x–z rectangles (convex polygon clipping, Sutherland–Hodgman) × y-overlap, divided by the union volume

- [ ] **Step 1: Write the failing tests**

```python
def test_two_crates_a_metre_apart_are_two_instances(): ...
def test_sparse_floaters_are_not_instances(): ...                     # 20 random points → []
def test_a_box_rotated_30_degrees_is_recovered():
    box = fit_box(sample_box(center=(1, 0.4, 2), size=(1.2, 0.8, 0.6), yaw=math.radians(30)))
    assert angle_close(box.yaw, math.radians(30), tol_deg=2)      # modulo 90°, size axes swapped accordingly
    assert np.allclose(sorted(box.size), sorted((1.2, 0.8, 0.6)), rtol=0.05)
def test_one_tall_outlier_does_not_stretch_the_height(): ...          # 1–99 percentile on y
def test_identical_boxes_have_iou_one(): ...
def test_square_box_rotated_90_degrees_has_iou_one(): ...
def test_disjoint_boxes_have_iou_zero(): ...
def test_half_overlap_along_x_is_one_third(): ...
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** `sklearn.cluster.DBSCAN(eps=DBSCAN_EPS_M, min_samples=DBSCAN_MIN_SAMPLES)` per label; drop clusters under `MIN_INSTANCE_POINTS = 60`. Yaw is the minimum-area rectangle of the x–z convex hull (`scipy.spatial.ConvexHull`): try each hull edge angle and keep the one with the smallest rotated extent area. Height spans the 1st–99th percentile of y (`HEIGHT_TRIM_PERCENTILES = (1, 99)`).
- [ ] **Step 4: PASS; commit** `feat(labeling): DBSCAN instances with gravity-aligned oriented boxes`

### Task 7: Batch CLI → `data/semantic_objects.json` (≈30 min)

**Files:** Create `scripts/label_scene.py`, `backend/src/infra/labeling/semantic_objects.py`; Modify `backend/src/infra/spatial/segmentation.py` (`SceneObject.yaw: float = 0.0`, last field, so existing constructors keep working); Test `backend/tests/unit/infra/labeling/test_label_scene.py`

**Interfaces:**
- Consumes: Tasks 2–6.
- Produces: `label_scene(cloud: PointCloud, views: List[CapturedView], segment: Callable[[np.ndarray], List[MaskDetection]], cache_dir: Path) -> List[Instance]` (pure orchestration; the segmenter is injected).
- `write_semantic_objects(path: Path, instances: List[Instance], view_count: int) -> None` and `read_semantic_objects(path: Path) -> List[SceneObject]`. Schema: `{"version": 1, "source": "Equipment Room.ply", "generated_at": ISO, "view_count": int, "objects": [{"id": "SEM-001", "label": "CRATE", "center": [x,y,z], "size": [w,h,d], "yaw": rad, "confidence": 0..1, "point_count": int}]}`. IDs are numbered by label, then x.
- CLI: `python scripts/label_scene.py [--views data/labeling/views] [--out data/semantic_objects.json] [--reuse-masks]`. Masks are cached per view in `data/labeling/masks/<view_id>.npz` (`np.packbits`), so re-running fusion is seconds.

- [ ] **Step 1: Write the failing tests**

```python
def test_two_views_of_a_synthetic_crate_produce_one_crate(tmp_path):
    instances = label_scene(synthetic_cloud(), two_synthetic_views(), fake_segmenter_masking_the_crate, tmp_path)
    assert [i.label for i in instances] == ["CRATE"]
    assert box_iou(instances[0].box, TRUE_CRATE_BOX) > 0.6

def test_json_round_trip_keeps_label_box_and_yaw(tmp_path): ...
def test_cli_exits_non_zero_with_a_reason_when_no_views(tmp_path): ...   # "no captured views in …"
```

- [ ] **Step 2: Run, expect FAIL.** — [ ] **Step 3: Implement.** — [ ] **Step 4: PASS.**
- [ ] **Step 5: Run it for real.** `backend/.venv/bin/python scripts/label_scene.py`. Expected: prints per-label counts and writes `data/semantic_objects.json`. Commit the JSON together with the code: `feat(labeling): batch labeling CLI and semantic objects file`

### Task 8: Use semantic objects in the simulator (≈35 min)

**Files:**
- Modify: `infra/spatial/scene_pipeline.py` (merge plus `"yaw"` in frames), `infra/spatial/asset_mapping.py` (`PREFERENCES`), `infra/paths.py` (`SEMANTIC_OBJECTS_PATH`), `frontend/src/js/app.js` (rotated frames and footprint)
- Test: `backend/tests/unit/infra/spatial/test_semantic_merge.py`, plus additions to `test_asset_mapping.py`

**Interfaces:**
- Consumes: `read_semantic_objects` and `SceneObject.yaw` (Task 7), `drop_covered` (`infra/spatial/placements.py`).
- Produces: `merge_semantic(geometric: List[SceneObject], semantic: List[SceneObject]) -> List[SceneObject]`, which drops geometric objects at least 50% covered by a semantic box and returns semantic plus the rest. Frames gain `"yaw"` (radians).

- [ ] **Step 1: Write the failing tests**

```python
def test_semantic_boxes_replace_the_geometric_fragments_they_cover(): ...
def test_missing_or_malformed_semantic_file_leaves_geometric_objects(tmp_path): ...  # read returns [] + warning
def test_a_pump_asset_prefers_a_detected_pump_over_a_floor_machine():
    objects = [obj(1, "FLOOR_MOUNTED_MACHINE"), obj(2, "PUMP", 3.0)]
    bindings = bind_assets(objects, [asset("A1", "PROCESS_PUMP")], "A1", *near(objects))
    assert bindings["OBJ-002"].asset["asset_id"] == "A1"
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Put the semantic labels first in `PREFERENCES` (`PROCESS_PUMP: ("PUMP", "FLOOR_MOUNTED_MACHINE", …)`, `ELECTRIC_MOTOR: ("ELECTRIC_MOTOR", …)`, `CONTROL_VALVE: ("VALVE", "HANDWHEEL", "VALVE_HANDWHEEL", …)`, `PRESSURE_TRANSMITTER: ("PRESSURE_GAUGE", "FIELD_INSTRUMENT", …)`). `run_pipeline` calls `merge_semantic(extract_objects(...), read_semantic_objects(SEMANTIC_OBJECTS_PATH))` before placements. Make `drop_covered` yaw-aware, or use the semantic box's axis-aligned hull (state which in the commit). Frontend: `box.rotation.y = frame.yaw || 0` in `buildFrames`, and rotate the robot position into the box frame in `distanceToFootprint`. Keep the occupancy grid point-based: it already follows the true geometry, and boxes would only coarsen it.
- [ ] **Step 4: PASS, restart `./run.sh` and verify live.** The labels read as crate, valve, pump…, the boxes sit on the objects in the photoreal view, a walk shows them in "Near the robot", and the console is clean.
- [ ] **Step 5: Commit** `feat(scene): semantic objects drive frames, binding and proximity`

### Task 9: Measure accuracy against hand-labeled ground truth (≈30 min)

**Files:** Create `scripts/eval_labels.py`; Modify `frontend/src/js/authoring.js` ("Save as ground truth" with a label `<select>` from the vocabulary, saved via `PUT /api/labeling/ground-truth/{id}` to `data/labeling/ground_truth.json`, reusing `JsonRecordStore`); Test `backend/tests/unit/infra/labeling/test_eval_labels.py`

**Interfaces:**
- Consumes: `box_iou`, `OrientedBox` (Task 6); `read_semantic_objects` (Task 7).
- Produces: `match(predicted: List[LabeledBox], truth: List[LabeledBox], iou_threshold: float = 0.25) -> Score(matched, precision, recall, label_accuracy)` with `LabeledBox(label: str, box: OrientedBox)`; greedy matching by highest IoU.
- CLI: `python scripts/eval_labels.py` prints one row per method (`Scene_Anchors`, `geometric`, `semantic`): matched, precision, recall at IoU ≥ 0.25, label accuracy among matches.

- [ ] **Step 1: Write the failing tests**

```python
def test_perfect_prediction_scores_one_everywhere(): ...
def test_right_box_wrong_label_counts_for_recall_not_label_accuracy(): ...
def test_each_truth_box_matches_at_most_one_prediction(): ...   # two overlapping predictions → 1 match, precision 0.5
```

- [ ] **Step 2: Run, expect FAIL.** — [ ] **Step 3: Implement.** — [ ] **Step 4: PASS.**
- [ ] **Step 5: Label ground truth.** Draw a box around 20+ objects with the `?author` lift tool (≈15 min), covering every vocabulary label present. Run the evaluation and paste the table into `README.md` under "Results".
- [ ] **Step 6: Commit** `feat(labeling): ground truth capture and accuracy report`

---

## Time plan for a 3-hour window

| Slot | Tasks |
|---|---|
| 0:00–0:20 | Task 0 spike (go/no-go) |
| 0:20–1:20 | Tasks 1–3 (rig, capture, back-projection); capture the 40 views as soon as Task 2 works |
| 1:20–2:15 | Tasks 4–7 (segmenter, fusion, boxes, CLI) and the first real `semantic_objects.json` |
| 2:15–2:50 | Task 8 (in the simulator) |
| 2:50–3:20 | Task 9 (numbers for the pitch) |

Cut order if time runs out: Task 9's frontend ground-truth button (label GT by editing JSON instead), then oriented boxes (ship `yaw = 0`), then the asset-binding preference change.
