# Starting a new visual annotation

The current observer is a capable conversation-window VLM. No model endpoint is wired into this release. To annotate a new cloud, an agent must actually inspect images and drive the tools; starting the HTML page or replaying actions does not perform fresh inference.

1. Declare the raw LAS input and Y-offset range before observing. `prepare` copies only coordinates and original record IDs into the inference archive; it does not copy semantic truth. Y offsets are metres from the LAS header minimum Y, left inclusive, right exclusive. This adapter currently supports LAS and Y stripes.
2. Use `LOOK` to inspect unfiltered projections in different directions, then `ZOOM` to inspect ambiguous regions. Image coordinates use 0–1000 across the complete PNG, origin top left. Height coloring represents geometry, not semantic truth.
3. State a `QUESTION` with a candidate explanation, alternatives and the next observation. Specify `PROPOSE.selections` explicitly in at least two views separated by 20 degrees. Region intersection maps selections back to original records; it does not extrapolate a wire or automatically connect fragments.
4. Actually inspect all generated unfiltered context images and candidate overlays. Record `REVIEW` as `support`, `contradict` or `unobservable`. Orange projections cannot provide independent visible evidence. Contradiction blocks submission; lack of evidence is not evidence against the alternative.
5. `CONFIRM` references the exact point hash and all reviewed context paths. New default sessions use `context_v1` and `delta_v1`. Each candidate needs actual visible support in two directions. This protocol threshold does not certify every selected point or whole-wire completeness.
6. After the last annotation change, `SURVEY` at least two unfiltered complete-ROI directions. Resolve questions or explicitly defer them using `UNKNOWN`. `FINISH` freezes annotation while retaining incomplete/unknown status. A frozen session cannot be edited in place.
7. For corrections, fork with `python -m visual_annotation_v3.revision OLD NEW`; then use `QUESTION → PROPOSE → PREVIEW_PATCH → REVIEW → PATCH`. Each changed set needs separate support. Inspect `review_protocol.py` and the tested examples for exact action fields.
8. Export after freezing. Ground truth may only be opened by the separate evaluator after the outputs are frozen.

Minimal first observation:

```json
{
  "action": "LOOK",
  "view_id": "first_top",
  "kind": "top",
  "size": 2048,
  "observer": "conversation_vlm",
  "reason": "Inspect the complete declared ROI to discover visible wires and competing structures."
}
```

Use the action dictionaries in `tests/test_visual_annotation_context.py` as protocol examples, and `examples/recorded_roi/actions.jsonl` for actual historical model choices. The shipped historical ROI uses the old `legacy_v0` protocol; replay preserves it rather than pretending it passed newer context review rules.

The software's `observer` field is caller-supplied provenance. It cannot authenticate a model identity or prove an image was viewed. Quality requires actual image inspection and independent evaluation; a valid JSON trace alone is not proof of visual understanding.

## Agent handoff

After installing this package, `python tools/observer_packet.py runs/my_scene` prints image paths, image hashes, camera metadata, pending candidate reviews and unresolved questions for a visual agent. It validates the geometry-only archive and does not read the source LAS or any evaluation file. It neither invokes a model nor invents a semantic decision.

Keep a single writer per session. Save the actual visual judgment in every action's `observer` and `reason` fields. Do not label copied or automatically generated decisions as a new model observation.
