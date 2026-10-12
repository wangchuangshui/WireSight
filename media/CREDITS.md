# Film credits

WireSight project introduction: documentary presentation assembled from the project's recorded conversation decisions, original evidence projections and frozen point coordinates. No new annotation inference is performed while the film plays.

- Data and derived projections: GridNet-HD, Antoine Carreaud et al., 2026; CC BY 4.0. Full attribution: `docs/DATA_ATTRIBUTION.md`.
- Visuals: actual point coordinates rendered by `demo/viewer.js`; exact recorded model selections from `demo/path-data.js`; actual evidence PNGs from the historical runs. No inferred points or gap-bridging lines are added for presentation.
- English narration: locally synthesized with [Piper](https://github.com/OHF-Voice/piper1-gpl), `en_US-lessac-high` voice ([voice card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/high/MODEL_CARD)). The source voice card is also preserved in `VOICE_MODEL_CARD.txt`. This is a synthetic English documentary narration, not the original model's voice or verbatim answer.
- Audio supplied: individual narration WAVs and assembled narration. The recorder uses the supplied audio; the release does not require a speech model to play or re-render the film.
- Storyboard and narration script: `film-plan.json`, `film-script.json`; rendered film source: `demo/film.html`, `film.css`, `film.js`.
- Captions: exact deterministic chapter timing, separate SRT/VTT plus burned-in English text. No music or third-party stock footage.

The uncolored/colored 3D comparison shows the same display point set; it is not an unfiltered full raw-input cloud. Original model input projections are explicitly shown in the evidence chapters. The support/unobservable example is a separate local revision and is not merged into the displayed full-scene result.
