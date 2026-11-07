# Demo acceptance criteria

The challenge demonstrator is ready when a local, repeatable run proves the following complete flow:

1. Load and process the provided `Industrial Boiler Room.ply`.
2. Show multiple extracted candidate objects with visible 3D frames.
3. Load the provided builder pack and display its asset/condition information.
4. Mark the association between scene objects and pack assets as synthetic wherever applicable.
5. Designate a faulty target.
6. Compute and validate a logical, collision-free route to that target.
7. Move a simulated avatar or robot along the route.
8. Dynamically highlight nearby framed assets and display their mapped information along the route.
9. At the target, present an evidence-grounded diagnosis with citations, confidence, observation/hypothesis separation, and safe next verification guidance.
10. Report route failure or missing/low-quality diagnostic evidence explicitly; do not produce success-shaped fallbacks.

## Submission checklist

- Runnable local demo and concise setup instructions.
- Source-code repository.
- Five to eight presentation slides describing scene extraction, navigation, metadata mapping, and the AI approach.
- Demo video of no more than five minutes showing the route, proximity display, and target diagnosis.
- Brief technical note listing models, libraries, and software components used.

## Quality checks

- The same inputs produce a repeatable target, mapping, and route.
- The route is checked against the obstacle representation before playback.
- Geometric detections, inferred labels, and synthetic data mapping are distinguishable.
- AI output cites the available source records and remains advisory.
- The viewer stays lightweight; mobile development is not required.
