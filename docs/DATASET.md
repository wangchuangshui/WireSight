# Dataset and exact reproduction

The demonstration uses the **official LiDAR point cloud for GridNet-HD, zone `t1z5b`**. It uses geometry rendered into height-aware projections, not the dataset's aerial RGB photographs.

| Item | Exact declaration |
|---|---|
| Dataset | [`heig-vd-geo/GridNet-HD`](https://huggingface.co/datasets/heig-vd-geo/GridNet-HD) |
| Pinned revision | `944b561090d1fed9803ccc96bfafb6ab3049726c` |
| Official file | `t1z5b/lidar/t1z5b.las` |
| File size | 2,265,716,708 bytes (about 2.27 GB) |
| File SHA256 / official LFS object | `11c9a2abf2eed1a6207a9bfeb5d2a00ea6f28ad09adbb40b0afcfdb0613fbd35` |
| Original record count | 59,624,089 |
| Official split | `val`; this project inspected and refined it as a development scene |
| Full-scene ROI | Y offsets `[0, 770.2)` metres from the LAS header minimum Y; all source X/Z |
| Shipped quick-replay ROI | Y offsets `[30, 60)` metres, 867,479 original records |
| Model input archive | Coordinates and original record IDs only; no semantic truth fields |
| Target for the reported point score | Raw class 5: conductor cable; raw 6/7: structural cable; scored together |
| Ignored raw classes | 12/13/255 |
| Truth field | `ground_truth`; native LAS `classification` is not a substitute |
| License | CC BY 4.0; separate [attribution](DATA_ATTRIBUTION.md) |

The official [dataset card](https://huggingface.co/datasets/heig-vd-geo/GridNet-HD/blob/944b561090d1fed9803ccc96bfafb6ab3049726c/README.md) and [split declaration](https://huggingface.co/datasets/heig-vd-geo/GridNet-HD/blob/944b561090d1fed9803ccc96bfafb6ab3049726c/split.json) document the source. Header scales, offsets and bounds are preserved in `examples/full_scene/manifest.json`. The source LAS declares EPSG:32632 (WGS 84 / UTM zone 32N) in its projection metadata; this package performs no CRS transformation. The display uses translated float32 coordinates; authoritative labels refer to original LAS records.

Use Python 3.12 for the tested dependency pins. The executor supports Python 3.10+, but older Python versions need compatible dependency versions and are not the exact image-hash reproduction environment.

## 1. Replay the included real ROI, without downloading the LAS

```bash
python -m pip install -e . -c requirements-tested.txt
OPENBLAS_NUM_THREADS=4 python tools/replay_example.py --out replay-output
python -m visual_annotation_v3.artifacts replay-output --las
```

Expected: 25 stored actions, 867,479 original records, `point_labels_identical: true`, `model_invoked: false`, `ground_truth_read: false`. Geometry, action trace and reference labels are bundled. This verifies original-point execution of saved visual choices.

## 2. Download the exact dataset file

```bash
python tools/download_data.py --out data
```

The downloader uses the pinned revision, verifies both size and SHA256, and writes `data/t1z5b/lidar/t1z5b.las`. It refuses an existing file with a different hash. No Hugging Face account or model weights are needed for this public file.

If you already have the LAS:

```bash
python tools/download_data.py --verify-existing /path/to/t1z5b.las
```

The raw LAS is intentionally separate from the release ZIP. The pinned URL is also stored in `examples/full_scene/manifest.json`.

## 3. Recompute the complete published point result

```bash
python tools/evaluate_full_scene.py \
  --las data/t1z5b/lidar/t1z5b.las \
  --out full-scene-metrics.json
```

The package now includes **the complete frozen full-scene prediction in compact form**: `examples/full_scene/frozen_positive_labels.npz`. It stores all 245,957 confirmed original record IDs and their visual instance IDs. Every other record in the declared 59,624,089-record scope has instance 0 (unconfirmed). This represents the complete label array without shipping a redundant zero for every background record.

The evaluator streams **every original record** from the verified LAS. It does not restrict recall to selected records or displayed context. All 252,541 target records remain in the denominator; unknown targets count as false negatives.

Expected:

```text
TP 245931   FP 26   FN 6610
Precision 99.98942904654065%
Recall    97.38260322086315%
```

The tool checks the frozen prediction hash and must report `matches_published_combined_metrics: true`. It also reports original-class recalls, 10m spatial bins, false-positive source classes and instance point counts. Instance identity/endpoint/length quality is not evaluated because independent instance truth is absent.

## 4. Re-execute the full recorded decision chain

```bash
python tools/replay_dataset.py --scope full --dry-run
OPENBLAS_NUM_THREADS=4 python tools/replay_dataset.py \
  --scope full \
  --las data/t1z5b/lidar/t1z5b.las \
  --out full-replay
```

This prepares geometry from the verified source, preserves each historical protocol, and re-executes four recorded visual sessions:

| Session | Y-offset scope | Saved actions |
|---|---:|---:|
| `t1z5b_full_session` | `[0,770.2)` | 38 |
| `tower_mid_refinement` | `[395,420)` | 11 |
| `tower_far_refinement` | `[640,670)` | 17 |
| `conversation_tower_attachment_20261011` | `[100,110)` | 33 |

The first three are composed; the attachment result is added using the **stored explicit instance associations**. The final positive IDs and instance IDs are compared with the bundled frozen reference. All remaining records stay zero. No model is called, no fresh associations are inferred, and ground truth is not read by this route.

Full rendering of nearly 60M records can require tens of GB of RAM and several GB of free disk. Start with the included small ROI for a quick check. Thread limits reduce unnecessary CPU oversubscription; no GPU is required by the executor. The saved image hashes were validated on Linux / Python 3.12 with `requirements-tested.txt` and DejaVu Sans fonts. Different font/raster-library builds can change image bytes even when point geometry is identical; a diverging image check fails explicitly. `--geometry-cache` is an optional acceleration for already prepared historical geometry; every cached file must match the frozen archive hash. Fresh preparation checks the exact uncompressed NPY payload hashes when historical compression produces different NPZ bytes. Coordinates and original record IDs must remain byte-identical; no tolerance or point substitution is used.

To check preparation directly from the LAS on the small ROI:

```bash
OPENBLAS_NUM_THREADS=4 python tools/replay_dataset.py \
  --scope roi --las data/t1z5b/lidar/t1z5b.las --out roi-from-las
```

## 5. Fresh visual annotation is a different experiment

Stored-decision replay and score recomputation are reproducible execution/evaluation. Fresh annotation requires a capable visual observer to inspect images and make new choices. The historical trace records `conversation_vlm` provenance, but does not lock a redistributable model checkpoint or certify unattended repeatability. Use [the observer guide](OBSERVER_GUIDE.md) for a new cloud.

Historical development refinements used knowledge of aggregate evaluation weaknesses. This is not an independent blind experiment or an official hidden-test leaderboard result.

## Verified release result

For 0.2.0, both the 25-action ROI and all four full-scene sessions were prepared directly from the verified original LAS, with no geometry cache. All 99 full-chain actions, composition and explicit associations produced identical final point labels; the final annotation archive SHA256 also matches the original frozen output. Complete-score recomputation matches the published combined score, all three class recalls, all 78 spatial bins and all seven instance counts. Actual reports are in `evidence/roi_from_dataset_replay.json`, `evidence/full_dataset_replay.json`, `evidence/full_scene_recomputed.json` and `evidence/full_score_reference_comparison.json`. These are saved-decision execution checks, not fresh model runs.
