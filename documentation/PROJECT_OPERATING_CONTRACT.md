# Project Operating Contract

> Project-specific knowledge. Universal methodology lives in the central `principal-ds` skill — do not copy it here.
> Label claims: VERIFIED / INFERRED / ASSUMED / HYPOTHESIS / UNKNOWN.

## Problem
Given a plate-appearance scenario (batter, pitcher, stadium, weather, game state), recommend where to position the seven non-battery fielders to maximize expected outs relative to the standard alignment, subject to MLB 2023+ shift-legality rules and the park's outfield fence. The system also scores user-arranged alignments. [INFERRED from `services/alignment/engine.py`, `app_structure.md`]

## Decision / action supported
A coach or analyst consuming the app's `POST /api/v1/alignments/recommend` output decides fielder placement pre-pitch. The UI shows top-N candidate alignments each with a `predicted_oaa_delta`, `predicted_hit_pct`, and a `confidence`. [INFERRED]

## Analytical unit
- **Prediction unit**: one scenario → one alignment `{position: (x, y)}` on the normalized 0–1 field grid. [VERIFIED]
- **Underlying data grain**:
  - `pitch_appearance` — one row per pitch (`mlb_play_id` dedupe key). [VERIFIED]
  - `batter_spray_profile` — one row per (player, season, scenario, fielding_zone), scenario = (pitch_type, pitcher_hand, speed_band); all-NULL scenario = "all". [VERIFIED]
  - `fielding_profile` — one row per (player, season, position). [VERIFIED]
  - `pitcher_profile` — one row per (pitcher, season). [VERIFIED]

## Target
**There is no trained/learned target.** The engine is a deterministic heuristic pipeline (`compute_alignment`):
1. Build ground + air hit-probability grids as a mixture of 8 hand-placed Gaussian "zone" blobs weighted by `hit_pct * sample_n` per zone, then normalized to sum to 1. [VERIFIED]
2. Build fielder coverage grids from time-to-reach radii (linear decay from center). [VERIFIED]
3. "Expected outs" = Σ(hit_prob_grid × coverage); `predicted_oaa_delta` = expected outs(candidate) − expected outs(standard). [VERIFIED]

`predicted_hit_pct = 1 − expected_outs`. Because the hit-probability grid is normalized to a spatial distribution of hit-mass, `expected_outs` is a **covered fraction of hit-mass**, not a calibrated out probability; `predicted_hit_pct` is therefore a unitless coverage complement, **not** a real hit rate. [INFERRED — flagged in TRUST_REPORT P0/P1]

## Prediction horizon
Live, pre-pitch. The recommendation is made at decision time using present-day fielder profiles and a recency-weighted blend of all available seasons of the batter's spray data. Outcome (out vs. hit) would be realized on the very next batted ball. [INFERRED]

## Prediction-time information
At live decision time the inputs (latest fielding profile, all-season spray blend, current pitcher profile, manual/forecast weather) are legitimately available. **For any retrospective evaluation**, note: (a) `get_latest_profile` returns the newest fielding profile regardless of scenario date → future data for historical scenarios; (b) season-aggregate spray for season S includes the outcome being predicted → target leakage if backtested naively. [INFERRED — see `documentation/leakage` notes in TRUST_REPORT]

## Evaluation
**Undefined.** No ground-truth metric, no holdout, no backtest against realized outs or Statcast OAA exists in the codebase. Existing tests validate mechanical properties (legality, radius monotonicity, candidate sorting), not predictive accuracy. [VERIFIED — `tests/unit/test_alignment_engine.py`]

## Baselines
The engine's own internal benchmark is the "standard" alignment (`STANDARD_POSITIONS`); every `oaa_delta` is measured against it. This is a **within-model** reference, not an external baseline. No external baseline (e.g., league-average positioning outcomes, actual team alignments) has been established. [VERIFIED]

## Validation design
None. Deployment represents a live single-pitch decision; no split, embargo, or holdout policy exists because nothing is trained or evaluated on outcomes. [VERIFIED]

## Leakage policy
No formal policy. Live use is leakage-free by construction (present-time inputs). The two retrospective-evaluation hazards above (latest-profile lookahead; season-aggregate spray containing the target) must be controlled before any accuracy claim. [INFERRED]

## Reproducibility requirements
- Engine is pure/deterministic given inputs (`services/alignment/engine.py`, no RNG). [VERIFIED]
- Tunables in `config.py` (`alignment_grid_size`=100, `spray_recency_decay`≈0.72, `alignment_*`). [VERIFIED]
- Data bootstrap: `scripts/seed`, `scripts/ingest_all --season …`, `scripts/ingest_historical` (2016–2025), `scripts/smoke`. Re-runs idempotent (pitches deduped, spray rebuilt per season). [VERIFIED from CLAUDE.md/app_structure.md]

## Known limitations
- Only 8 coarse fielding zones; zone centers/sigmas hand-tuned. [VERIFIED]
- `fielding_zone` derived by nearest-of-8-centers from `hc_x/hc_y` with a self-described "rough normalization" (magic constants). [VERIFIED]
- Range model uses a single 400-ft normalization and an outfielder-oriented sprint model for all positions; default sprint 27 ft/s. [VERIFIED]
- `confidence = 0.30 + sample_n/400` is arbitrary, not a calibrated uncertainty. [VERIFIED]
- No output has been validated against real defensive outcomes → EXPLORATORY trust. [VERIFIED]

## Open questions
- What realized-outcome data could serve as ground truth (Statcast OAA by fielder/zone; hit-vs-out on batted balls given actual alignment)?
- Is the app's intended claim "physically plausible suggestion" or "predicts out conversion"? This determines the required validation bar. [UNKNOWN]
- Are the normalized coordinate transforms (spray ingest `hc_x/hc_y` → grid; 1 unit = 400 ft) calibrated against known field landmarks? [UNKNOWN]
