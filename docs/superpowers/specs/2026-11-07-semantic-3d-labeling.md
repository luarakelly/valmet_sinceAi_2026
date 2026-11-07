# Semantic 3D labeling of the Equipment Room splat — spec

## Problem (from the team, 7 Nov 2026)

We are building a 3D training simulator for new hires on the provided Gaussian splat (`data/Equipment Room.ply`):
trainees walk around (point-and-click A* exists) and interact with equipment, with AI help. The bounding boxes
in the provided data are wrong: mislabeled (crates named pipes), at the wrong place, or partly right but
mis-sized. We need an automated way to label everything in the scene as accurately as possible and draw
accurate 3D bounding boxes.

## Required approach (verbatim blueprint)

Render RGB-D + Grounded-SAM 2 + 3D back-projection + DBSCAN.

1. Salvage or sweep: no `cameras.json` ships with the scan, so spawn virtual cameras (20–50 views) along
   walkable A* positions looking outward and render RGB + depth + camera matrix.
2. Detect & unproject: run Grounded-SAM 2 (GroundingDINO or YOLO-World + SAM 2) on the RGB frames with the
   prompt list `["crate", "pipe", "valve", "fire extinguisher", "pallet", "hazard"]`. For every 2D mask, take the
   3D Gaussians whose centres project inside the mask AND whose depth matches the rendered depth within ±15 cm.
3. Cluster & fit: DBSCAN (`eps=0.1`, `min_points=30`) per class to split instances and drop floaters; fit
   axis-aligned or oriented boxes; export JSON; feed the boxes into the scene, obstacle avoidance and trainee
   interaction triggers.

## Facts that constrain the design (checked 7 Nov)

- No training cameras exist; only the splat. The viewer already renders it photoreal (Spark, Three.js) and the
  `?author` panel already captures a clean canvas + the exact `view_projection` (three.js column-major).
- Backend venv: Python 3.14, CUDA torch 2.15, ultralytics (YOLO-World, SAM 2). Not installed: transformers
  (GroundingDINO), scikit-learn (DBSCAN). No open3d.
- Scene frame: metres, Y up, floor at y = 0 (`infra/spatial/point_cloud.py`). Canonical cloud: 671,032 points.
- The workbook's `Scene_Anchors` boxes are placeholders on a 30 × 15 m grid; the room is about 9 × 7 m.
- Current geometric segmentation finds 533 unlabeled-by-meaning objects in this room (shape labels only).
- YOLO-World returned 0 detections on earlier renders of the previous scan, even at confidence 0.05.

## Success criteria

- `data/semantic_objects.json` with labeled, gravity-aligned oriented boxes for the room's equipment.
- On a hand-labeled set of ≥ 20 objects: recall ≥ 0.7 at 3D IoU ≥ 0.25 and label accuracy ≥ 0.8 among matches,
  reported next to the `Scene_Anchors` and geometric-segmentation baselines.
- The viewer, proximity display, asset binding and copilot use the new boxes with no other change for the user.
