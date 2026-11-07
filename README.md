
# Ask Your Factory

### Conversational Spatial Intelligence for Industrial Digital Twins

**Since AI Hackathon 2026 | Challenge Partner: Valmet Automation**

## Run:

1. Copy `.env.example` to `.env`; optionally add `GEMINI_API_KEY` (without it the deterministic evidence engine answers).
2. Install [uv](https://docs.astral.sh/uv/).
3. Initialize once, then run:
	- **Linux:** `./initialize.sh`, then `./run.sh`
	- **Windows:** `initialize.bat`, then `run.bat`
4. Open `http://localhost:8000`, press **Start**: the robot walks to the faulty pump and the copilot diagnoses it.
5. Tests: `cd backend && .venv/bin/python -m pytest -q`

## Results on `Industrial Boiler Room.ply`

| Challenge requirement | What the pipeline does | Measured |
|---|---|---|
| Extract & 3D-frame assets | Splat → canonical Y-up cloud → voxel components split at thin links / sparse planes → geometric + colour labels | **144 framed objects** (pipe runs, fittings, valves, floor machines, instruments) from 207 k splats in **0.55 s** |
| Map Excel metadata | Pack assets bound to compatible, reachable objects with `mapping_confidence` | **30 / 30 assets** bound; target = lowest health (**P-005**, fouling, 44/100) |
| Collision-free navigation | Obstacle grid (ankle → robot height), robot-radius inflation, A* + line-of-sight smoothing; clearance re-measured on the final route | **6.4 m** route, min clearance **0.226 m** ≥ robot radius 0.22 m; every asset route tested collision-free |
| Proximity display | Frames within 1.0 m of the robot (to the box edge) light up; every mapped asset it passes is briefed in a route log, and each of the 114 unmapped structures shows the nearest Excel asset as context | updates every frame |
| AI diagnostics | Telemetry drift (Welch t-score vs own baseline), matching alarms, similar service cases, docs, data-quality confidence penalty; optional Gemini answer accepted only if every cited ID exists | P-005: flow −8.7 % (t = −4.8), 3 fouling alarms, 2 matching cases, confidence 0.91 → 0.61 from 9 data-quality issues |

Pipeline details: [`stack.md`](stack.md). Code map: [`fileStructure.md`](fileStructure.md).

Ask Your Factory is an AI-powered conversational spatial intelligence system that enables industrial field-service personnel to interact with complex industrial environments through natural language.

By combining semantic 3D scene understanding, spatial reasoning, equipment relationships and generative AI, the system transforms a traditional industrial digital twin into an intelligent, queryable environment.

Instead of manually searching through industrial equipment and technical documentation, users can simply ask questions and receive contextual answers directly within the 3D environment.

---

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
