# Use cases

## UC-01 — Inspect the processed industrial scene

**Primary actor:** Service technician or demo viewer  
**Goal:** Understand the scene and the objects extracted from it.

**Main flow**

1. The user opens the demonstrator.
2. The system displays the boiler-room scene with extracted objects framed.
3. The user selects or inspects a frame and sees its detected label, bounds, and extraction confidence.
4. If pack data has been mapped, the user sees the synthetic-mapping indicator and associated asset status.

**Outcome:** The user can distinguish extracted geometry from inferred labels and synthetic metadata.

## UC-02 — Navigate to the faulty target

**Primary actor:** Service technician  
**Supporting system:** Navigation planner and simulation  
**Goal:** See a simulated worker or robot follow a safe route to the selected faulty device.

**Main flow**

1. The system selects or loads the predetermined faulty target.
2. The planner computes a route over the walkable area.
3. The route is checked against the obstacle representation.
4. The viewer shows the route and moves the avatar/robot along its waypoints.
5. The viewer updates nearby framed assets and their mapped metadata as the avatar/robot moves.

**Alternative flow:** If no valid route is found, the system reports that navigation is unavailable instead of displaying a route through an obstacle.

**Outcome:** The target and the route are clear, and nearby assets are surfaced along the path.

## UC-03 — Review target condition and service guidance

**Primary actor:** Service technician  
**Supporting system:** Diagnostic assistant  
**Goal:** Understand why the target was flagged and what to verify next.

**Main flow**

1. The avatar/robot reaches the target.
2. The system gathers available target telemetry, condition events, knowledge records, and service cases.
3. The assistant presents an observation, a clearly separated hypothesis, confidence, and evidence references.
4. The assistant suggests a safe next verification step and defers to site procedures and qualified personnel.

**Alternative flow:** If evidence is missing or low quality, the system says so, lowers confidence, and avoids unsupported conclusions.

**Outcome:** The user receives explainable, advisory guidance; no physical action is initiated.

## UC-04 — Load the challenge data

**Primary actor:** Demo operator  
**Goal:** Prepare the scene and asset data for a repeatable demonstration.

**Main flow**

1. The operator points the local application at the provided PLY and workbook.
2. The importer validates and loads the supported records.
3. The system reports missing or invalid input clearly.
4. The scene and pack records are available to the other use cases.

**Outcome:** A local run is reproducible without a live broker or external telemetry producer.
