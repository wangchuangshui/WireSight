# Data attribution

The real-scene evidence in this release is derived from **GridNet-HD** by Antoine Carreaud, Shanci Li, Malo De Lacour, Digre Frinde, Jan Skaloud and Adrien Gressin (2026).

- Dataset: https://huggingface.co/datasets/heig-vd-geo/GridNet-HD
- Paper: https://arxiv.org/abs/2601.13052
- DOI: https://doi.org/10.57967/hf/9320
- Dataset license: **CC BY 4.0**, https://creativecommons.org/licenses/by/4.0/
- Dataset card checked on 2026-10-12: https://huggingface.co/datasets/heig-vd-geo/GridNet-HD/blob/main/README.md

Changes made here: geometry-only orthographic projections, height/ink rendering, candidate overlays, visual point annotations, background display sampling, coordinate translation and interactive presentation. These are project-derived artifacts, not annotations supplied or endorsed by the dataset authors.

`demo/audit/assets/`, the embedded coordinates in `demo/scene-3d.html`, `examples/recorded_roi/geometry.npz`, and the evidence images shown in screenshots/video contain dataset-derived material. The dataset license and attribution apply to that material separately from the software license. The bundled ROI contains no ground-truth fields. Raw LAS files and complete full-scene geometry are not bundled.

The public demonstration uses t1z5b, an inspected development scene. It is not a hidden-test or official leaderboard result. The point metric aggregates raw conductor and structural cable classes 5/6/7; unassigned classes 12/13/255 are excluded as declared. The dataset supplies semantic labels; it does not certify this project's wire instance associations.
