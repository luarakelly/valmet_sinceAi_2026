# User stories

Stories are ordered by challenge value. “Must” stories define the end-to-end demonstrator; “Should” stories improve clarity and reliability.

## Must

### US-01 — Extract and frame scene objects

As a demo viewer, I want objects in the supplied boiler-room scene to be extracted and framed so that the environment has visible semantic structure.

**Acceptance criteria**

- The pipeline processes the provided PLY and produces multiple candidate scene objects with 3D bounds.
- The viewer renders a frame for each produced object.
- Extraction labels and confidence are presented as detections or inferences, not ground truth.
- Re-running with the same input produces repeatable results.

### US-02 — Load and associate builder-pack records

As a demo viewer, I want scene objects associated with builder-pack asset information so that the environment shows meaningful statuses and metadata.

**Acceptance criteria**

- The system imports the supported asset and condition data from the supplied workbook.
- A faulty target is visibly designated.
- Each association indicates that the mapping is synthetic when it is random or procedural.
- The mapping is repeatable across demo runs.

### US-03 — Navigate around obstacles

As a service technician, I want an avatar or robot to follow a walkable route to the faulty target so that the simulation represents plausible field service.

**Acceptance criteria**

- The system derives or loads a walkable representation and obstacles.
- The route is automatically computed and checked against the obstacle representation.
- The viewer does not animate a route known to intersect an obstacle.
- If no route can be found, the system reports the failure clearly.

### US-04 — See assets near the route

As a service technician, I want nearby framed assets and their mapped information to update as the avatar moves so that I can understand its surroundings.

**Acceptance criteria**

- Nearby assets are determined from a documented proximity radius.
- The viewer highlights nearby frames and displays available mapped metadata.
- The display updates at multiple points along the route.

### US-05 — Get grounded target guidance

As a service technician, I want a concise, evidence-grounded explanation at the faulty target so that I can decide what to verify next.

**Acceptance criteria**

- The response cites available telemetry, event, or knowledge-record identifiers.
- It separates observed data from hypotheses and states confidence.
- It proposes a safe verification step and does not direct autonomous physical action.
- Missing or low-quality evidence lowers confidence and is disclosed.

## Should

### US-06 — Run a repeatable local demo

As a demo operator, I want to run the complete experience locally from the supplied files so that the demonstration does not depend on external streaming infrastructure.

**Acceptance criteria**

- Setup and run instructions are documented.
- The same inputs produce the same selected target, mapping, and route.
- Changing telemetry during playback, if needed, uses a local deterministic replay.

### US-07 — Understand uncertainty

As a demo viewer, I want detected geometry, inferred labels, and synthetic mapping clearly distinguished so that I do not mistake prototype output for verified plant data.

**Acceptance criteria**

- The interface labels synthetic mappings.
- Extraction and mapping confidence are shown when available.
- The diagnostic distinguishes evidence from inference.
