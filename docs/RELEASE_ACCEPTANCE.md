# Release acceptance / 0.2.0

This release completes the English-primary wire-project presentation and reproducibility package. It adds an interactive result-first page, exact recorded visual-path overlays and a 94-second English introduction. Frozen labels and development-scene point metrics are unchanged. Multiclass work remains deferred.

| Acceptance item | Evidence |
|---|---|
| Real interactive first-screen result, original top-down input and eight guided chapters | `demo/index.html`, `evidence/browser_validation.json` |
| Five main colors visibly rendered and each instance isolated; camera controls work | `evidence/browser_validation.json` |
| 387 evidence images, all 499 steps in ten archived sessions, no external requests, mobile layout | `evidence/browser_validation.json` |
| English landing page, self-contained 3D page and all nine film scenes | `evidence/english_presentation_validation.json` |
| 94.0s, 1600×900, H.264/AAC, English synthetic narration and captions | `evidence/video_validation.json`, `media/CREDITS.md` |
| Pinned public dataset URL accessible without credentials; exact local file SHA256 checked | `evidence/dataset_download_validation.json`, `examples/full_scene/manifest.json` |
| Complete original-record score recomputed from LAS and shipped compact prediction | `evidence/full_scene_recomputed.json` |
| Four source sessions / 99 saved decisions, composition and explicit associations reproduce frozen point labels | `evidence/full_dataset_replay.json` |
| Direct preparation from pinned LAS and 25-action ROI replay produce identical geometry payloads and labels | `evidence/roi_from_dataset_replay.json` |
| Real bundled ROI replay and full ROI LAS export/readback in separate validation environment | `evidence/clean_environment_replay.json`, `evidence/clean_environment_las_readback.json` |
| 23 executor/review consistency and failure tests | `evidence/protocol_tests.xml` |
| Browser MP4 playback/seek and HTTP prefix/suffix/middle byte ranges | `evidence/live_service_validation.json` |
| Release member hashes and extracted-package validation | Root `RELEASE_MANIFEST.json`; acceptance report beside the ZIP |

Exact point scope: all 59,624,089 original records; all 252,541 target records remain in recall. TP=245,931, FP=26, FN=6,610; precision=99.989429%, recall=97.382603%. Target raw classes 5/6/7; ignored 12/13/255. Truth field is `ground_truth`.

The official source split is `val`, used here as an inspected and revised development scene. Historical refinements used aggregate evaluation weaknesses. This is not an independent blind held-out result. Stored-decision replay proves execution, not repeatability of new model observation. Endpoint/length completeness, independent instance identity and unattended success remain unverified. The separate local connection revision is not merged into the frozen full result.

Historical NPZ compression differs across sessions: fresh preparation and export may have different archive hashes while exact uncompressed geometry and label arrays match. Replay checks exact geometry member hashes, saved image/point decisions and final point arrays; it never accepts approximate coordinates.
