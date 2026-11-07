
# Ask Your Factory

### Conversational Spatial Intelligence for Industrial Digital Twins

**Since AI Hackathon 2026 | Challenge Partner: Valmet Automation**

## Run

1. Copy `.env.example` to `.env`; optionally add `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` (without a key the deterministic evidence engine answers).
2. Install [uv](https://docs.astral.sh/uv/) (or use `python -m venv` + `pip`).
3. Initialize once, then run:
	- **Git Bash (Windows) / Linux / macOS:** `./initialize.sh`, then `./run.sh`
	- **cmd / PowerShell:** `initialize.bat`, then `run.bat`
	- Without uv (Git Bash): `python -m venv backend/.venv && backend/.venv/Scripts/python -m pip install -r backend/requirements.txt && ./run.sh`
4. Open `http://localhost:8000`.
5. Tests: `cd backend && .venv/Scripts/python -m pytest -q` (Linux/macOS: `.venv/bin/python`).

The raw scan is required: put `Equipment Room.ply` (395 MB, not in git) in `data/` or `data/input/`. The viewer cloud, splat and mesh are generated from it on first start. To rebuild the mesh, put
`Equipment Room.ply` in `data/` or `data/input/` and run `backend/.venv/Scripts/python scripts/build_mesh.py`. Reseed the database with `scripts/seed_database.py --force`.

## Using the UI

The robot starts at the door. The faulty device (P-005) is pinned top left, and its route is drawn on the floor.

1. **Go** on the target card — the robot walks the collision-free route; assets within 1.5 m are listed under *Near the robot*.
2. **Click the blue floor** to walk anywhere, or **Route here** on any asset. The robot stops 0.8 m from the asset.
3. **Click a label** (or arrive at an asset) — the copilot panel shows observation, hypothesis, next safe check, confidence and the evidence IDs; the object is highlighted through walls (x-ray).

- Camera: **Follow robot** (drag = turn around the robot, wheel = zoom; it stays inside the room) or **Top** (plan view).
- Left list: target card, *Near the robot*, *Needs attention*, *Healthy*, *Detected objects* (all 144, by shape, with **Show all in 3D**).
- Ask in the bottom bar: “Why is P-005 flagged?”, “Which assets need attention?”, “Where is M-006?”, “Route to CV-003”. With an LLM key the copilot can also navigate, select, diagnose or reset.
- **View** menu: Photoreal (default), Point cloud, Height colours, **Verify placement (camera)** — a vision-language model looks at each object and says what it is. Free camera, YOLO and re-extraction are under `?debug=1`.
- Asset ↔ 3D object links are synthetic unless camera-verified, and are labelled with their mapping confidence.

## Results on `Equipment Room.ply`

| Challenge requirement | What the pipeline does | Measured |
|---|---|---|
| Extract & 3D-frame assets | Splat → canonical Y-up cloud → voxel components split at thin links / sparse planes → geometric + colour labels | **144 framed objects** (pipe runs, fittings, valves, floor machines, instruments) from 207 k splats in **0.55 s** |
| Map Excel metadata | Pack assets bound to compatible, reachable objects with `mapping_confidence`; every other object joins the nearest asset's system as a procedural component (allowed by the brief) | **30 / 30 assets** bound, **144 / 144 objects** carry pack metadata; target = lowest health (**P-005**, fouling, 44/100) |
| Collision-free navigation | Obstacle grid (ankle → robot height), robot-radius inflation, A* + line-of-sight smoothing; clearance re-measured on the final route; stops 0.8 m from the asset | **5.3 m** route to P-005, min clearance **0.24 m** ≥ robot radius 0.22 m; every asset route tested collision-free |
| Proximity display | Frames within 1.5 m light up; live list of nearby assets and their components with state, health and distance | updates every frame |
| AI along the route | Each pack asset the robot passes is explained in the copilot thread: status line for healthy devices, grounded evidence-engine diagnosis with citations for the rest | 21 devices explained on the P-005 walk |
| AI diagnostics | Telemetry drift (Welch t-score vs own baseline), matching alarms, similar service cases, docs, data-quality confidence penalty; optional Gemini answer accepted only if every cited ID exists | P-005: flow −8.7 % (t = −4.8), 3 fouling alarms, 2 matching cases, confidence 0.91 → 0.61 from 9 data-quality issues |

Architecture: [`docs/architecture.md`](docs/architecture.md). Pipeline details: [`docs/stack.md`](docs/stack.md). Code map: [`docs/file-structure.md`](docs/file-structure.md).

Ask Your Factory is an AI-powered conversational spatial intelligence system that enables industrial field-service personnel to interact with complex industrial environments through natural language.

By combining semantic 3D scene understanding, spatial reasoning, equipment relationships and generative AI, the system transforms a traditional industrial digital twin into an intelligent, queryable environment.

Instead of manually searching through industrial equipment and technical documentation, users can simply ask questions and receive contextual answers directly within the 3D environment.

---

## Automatic semantic labels (optional, GPU)

The geometric extraction cannot tell a crate from a pipe. This step names and boxes equipment from photoreal renders:

1. Start the server, open `http://localhost:8000/?author` and press **Capture labeling views** (40 virtual cameras on walkable floor; each image is saved with its exact camera matrix).
2. `backend/.venv/Scripts/python scripts/spike_grounded_sam.py` is the quick go/no-go check on a few screenshots in `data/labeling/spike/`.
3. `backend/.venv/Scripts/python scripts/label_scene.py` runs GroundingDINO + SAM 2 on every view, back-projects the masks onto the scan (±15 cm of the visible surface), votes across views (at least 2 must agree), clusters with DBSCAN (eps 0.10 m, 30 points) and writes `data/semantic_objects.json` plus an Excel coverage report (which of the 30 pack assets were found).
4. Restart the server: semantic objects replace the geometric ones they cover, carry the asset class, and are drawn as rotated boxes. Without the file everything behaves as before.
5. `scripts/eval_labels.py` scores the result against the boxes you confirmed with the placement tool.

## The Problem

Industrial environments contain complex networks of machinery, pipes, pumps, tanks and other equipment.

Field-service personnel often need to:

- Locate specific equipment within large industrial facilities.
- Understand spatial relationships between machines.
- Identify nearby equipment and potential obstacles.
- Navigate safely through industrial environments.
- Retrieve equipment conditions, alarms and maintenance instructions.
- Understand which equipment requires inspection or maintenance.

However, this information is often distributed across different systems, technical documentation and physical environments.

Traditional digital twins provide visualization, but interacting with and understanding the environment can still require manual exploration and technical knowledge.

## Our Solution

Ask Your Factory introduces a conversational AI layer directly connected to an industrial 3D environment.

Users can ask questions about equipment locations, spatial relationships, equipment conditions and maintenance requirements.

The AI interprets natural-language questions, retrieves relevant spatial and equipment information, and dynamically interacts with the 3D scene.

The system combines:

1. Semantic 3D scene understanding.
2. Conversational spatial intelligence.
3. Interactive 3D visualization.
4. Obstacle-aware autonomous navigation.
5. AI-powered maintenance assistance.

Our goal is to make industrial environments understandable and accessible through natural conversation.

---
