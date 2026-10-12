# What can be reproduced?

| Operation | Included | What it proves |
|---|---|---|
| Open the guided demo / video | Yes, offline assets | Inspect recorded visual decisions and the frozen result |
| Replay the bundled actual 30–60m ROI | Geometry, action trace and reference annotation included | Deterministic executor maps saved decisions to identical point labels |
| Annotate a new LAS ROI | Executor and observer protocol included | Requires a capable visual observer making new decisions |
| Replay all full-scene source sessions | Four original action traces, scopes and explicit associations included | Prepare geometry from the pinned LAS, then re-execute the full saved-decision chain |
| Recompute 59.6M-record P/R | Complete compact frozen prediction included; pinned raw LAS downloadable | Stream the full original LAS and verify published point metrics |
| Independently rerun the conversation VLM | No unattended model adapter included | Not established |

The ROI is a real geometry-only crop: 867,479 records, Y-offset [30,60) metres in t1z5b. Actions, state, geometry and reference annotation are copied byte-for-byte from the historical run; `scene.json` only replaces the raw LAS location and adds path prefixes for portable replay. `PROVENANCE.json` records original hashes. The code change to `replay.py` remaps historical paths; it does not modify selections.

Run in Python 3.12 for the tested dependency pins:

```bash
python -m pip install -e . -c requirements-tested.txt
OPENBLAS_NUM_THREADS=4 python tools/replay_example.py --out replay-output
python -m visual_annotation_v3.artifacts replay-output --las
```

The output's `replay_verification.json` must state `point_labels_identical: true`, `ground_truth_read: false`, `model_invoked: false`. LAS export reads the generated file back and verifies original IDs, instance IDs and coordinates. This confirms execution, not repeatability of model perception.

Full-scene result version: `t1z5b_full_conversation_refined`, annotation SHA256 `f8f802ee2d2d78730c39eefb68c81319a6e50a8554f5d78b5e0cd74213116437`. The HTML 3D viewer stores float32 translated display coordinates. Original full-precision coordinates are in the pinned source LAS. All confirmed original point IDs and instance IDs are included in `examples/full_scene/frozen_positive_labels.npz`; all other records have implicit instance 0. The viewer is not the authoritative annotation file.

The frozen full result has five main instances (233,548 points) and two transverse instances (12,409 points). There is no independent instance truth. The local `conversation_connection_revision_20261011` example adds 193 records to its own ROI baseline and is **not merged into this full-scene version**. Guided steps 05–06 deliberately show that separate branch. Do not mix its local metrics with the full result.

All original records remain in the evaluation denominator; unknown target records are false negatives. Target raw classes 5/6/7, ignored classes 12/13/255. The weakest 10m region remains at 650–660m, R=80.710098%. Known unresolved intervals are disclosed by the audit view; they are not a complete list of omissions.

Developer checks:

```bash
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest -q
python tools/validate_demo.py
python tools/verify_release.py
```

`tools/record_video.py` reproduces the presentation capture using Playwright and ffmpeg. It renders a documentary presentation from saved evidence and the actual point renderer, not a live model session. Supplied narration WAVs are used; no speech or annotation model is invoked by the recorder. Media credits and storyboard are in `media/`. FFmpeg/ffprobe and a browser with WebGL support are needed only for recording/checking the video.

Exact dataset download, complete-score recomputation and full decision-chain replay commands are in [DATASET.md](DATASET.md). The compact label form represents the complete original-record output; it does not narrow the evaluation scope.
