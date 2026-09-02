# Modeling

> Project-specific modeling knowledge: baselines, models, validation results, and what has been ruled out. Label claims: VERIFIED / INFERRED / ASSUMED / HYPOTHESIS / UNKNOWN.

## Nature of the "model"

The alignment engine is a **deterministic, hand-specified heuristic**, not a trained/statistical model. There are no learned parameters, no fitting, no RNG. All coefficients (zone centers/sigmas, reach radii, weather scales, pitcher clamp, confidence formula) are hard-coded. [VERIFIED — `services/alignment/engine.py`]

## Baseline ladder (permanent yardstick)

| Baseline | Metric | Value | Split | Date | Status |
|---|---|---|---|---|---|
| "standard" alignment (internal reference) | `oaa_delta` by construction = 0 | 0 | n/a | — | Internal only — **not an external baseline** [VERIFIED] |
| League-average positioning → out rate | — | — | — | — | **Not established** [VERIFIED] |
| Actual team alignment → realized out rate | — | — | — | — | **Not established** [VERIFIED] |

No external, outcome-based baseline exists. `predicted_oaa_delta` is defined *relative to the engine's own standard alignment*, so it cannot currently be checked against reality.

## Current "models" (heuristic components)

### Hit-probability grid — `build_hit_probability_grid`
- **Inputs**: 8 `BatterSprayProfile` zone rows; per-zone weight `hit_pct * sample_n`, optionally × trajectory share (ground/air). Weather rolls the grid laterally (crosswind) and in depth (carry). [VERIFIED]
- **Form**: sum of 8 fixed Gaussian blobs (hand-set centers `ZONE_CENTERS`, sigmas 0.08 infield / 0.12 outfield), normalized to sum 1 → a spatial distribution of hit-mass. [VERIFIED]
- **Weakness**: 8-zone resolution is coarse; centers/sigmas unvalidated against real landing-location density. [VERIFIED]

### Range / coverage model — `compute_reach`, `FielderReach.coverage_grid`
- Time-to-reach radii from `dist = (t − reaction) × sprint_speed × route_eff`, normalized by 400 ft. Coverage = linear decay from 1.0 at center to 0 at `r_300s`. [VERIFIED]
- **Weaknesses**: single 400-ft normalization treats the field as a 400-ft square; outfielder-oriented sprint model applied to infielders; linear (not physically-motivated) catch-probability decay; no arm/throw or double-play modeling. [VERIFIED]

### Scoring — `_expected_outs`, `score_alignment`, `compute_alignment`
- Infielders convert ground grid, outfielders convert air grid, with reduced cross terms (0.15 / 0.30). `optimize_for` reweights ground vs. air. Pitcher `groundball_pct` tilts ground/air weights (clamped 0.6–1.5). [VERIFIED]
- Greedy local search (`optimize_positions`) nudges fielders on a fixed offset set for ≤2 sweeps, keeping legal improvements. [VERIFIED]
- **Output semantics caveat**: `expected_outs` is a covered fraction of normalized hit-mass; `predicted_hit_pct = 1 − expected_outs` is therefore a coverage complement, not a calibrated hit rate. Numbers should not be read as literal out/hit probabilities. [INFERRED]

### Confidence — `_confidence_from_sample`
- `min(0.95, 0.30 + sample_n/400)`. Purely sample-size heuristic; **not** a calibrated interval. [VERIFIED]

## Validation results

**P0 out-model evaluation (2026-09-02)** — first outcome-linked result. On 472,327 standard-alignment in-play batted balls (2021–2025, LOSO), the engine's per-location coverage surface at the standard alignment was scored against realized out/hit. Full numbers in `EXPERIMENTS.md`. Headline: [VERIFIED]
- **Discrimination**: engine AUC 0.637 vs zone-lookup 0.581 (Δ +0.056, 95% CI [+0.053, +0.058]) — the coverage geometry ranks outs **better** than an 8-zone lookup, stable across all five seasons.
- **Calibration**: slope 0.369, intercept 0.627, log loss 4.45 vs baseline 0.61 — `coverage` values are **not probabilities**; ~half of balls get P(out)≈0 while ~59% are outs. Severe under-prediction, worst in fielder gaps.
- **Reading**: real spatial signal, badly miscalibrated output. Recalibrate, don't discard. Scope: validates P(out | standard), not the prescriptive `oaa_delta`.

**Recalibration experiment (2026-09-02) — PASS.** A per-trajectory (ground/air), out-of-fold **isotonic** recalibration of `coverage → P(out)` turns the surface into a valid probability that beats the zone baselines: log loss 0.582 (isotonic) / 0.586 (logistic) vs zone 0.607 and zone_traj 0.594 — CI-separated on both bars; reliability slope 0.99/1.00; Brier 0.199 vs 0.209. AUC rose 0.640 → 0.656 (per-trajectory maps add cross-trajectory discrimination). The margin over zone lookups is **real but modest** (~0.025 log loss vs plain zone; ~0.012 vs zone_traj). Transfer check: std-fit map stayed calibrated on shifted-alignment balls (slope 0.97, caveated). Full numbers in `EXPERIMENTS.md`. [VERIFIED]

Mechanical tests (`tests/unit/test_alignment_engine.py`) still cover implementation properties only (legality, radius monotonicity, sorting) — not accuracy. [VERIFIED]

## Ruled out / negative results

- **Stronger static `infield_shift` template — RULED OUT (2026-09-02).** To fix the under-predicted shift magnitude, a maximally-aggressive-but-legal template (1B/2B pulled to the RF line, SS/3B stacked just left of the bag) was tried; it *reduced* modeled coverage (predicted lift went negative, direction signal broke) by vacating the up-the-middle lane. A single static template can't be strongly pull-concentrated AND gap-free across batters. The magnitude/positioning fix belongs to **per-batter optimization** (`optimize_positions`), not a stronger fixed template. Gentle template retained; in-code NOTE added.
- **Per-batter optimization fixes magnitude but not per-batter discrimination (2026-09-02).** Scoring the engine's `optimize_positions` recommendation (vs the template) gives realistic shift magnitude (mean predicted lift +0.049 ≈ realized +0.025, vs template ~0) and correct direction with no handedness flag — but cross-batter correlation with realized lift is ~0 (pearson +0.02): it predicts a positive benefit for nearly every batter, so it can't rank who to shift. Circularity caveat: the optimizer maximizes coverage over the same grounders it's scored on → optimistic/compressed. Conclusion: curation is the right mechanism; the per-batter shift *decision* is a separate, not-yet-validated question → Part 2 (off-policy) + fine-placement data.
- **Engine shift recommendation was handedness-naive — FOUND & FIXED (2026-09-02, P1 Part 1).** Originally `suggest_shift_type` (`pull_zones={1,2}`) and `default_positions_for_shift("infield_shift")` treated "pull" as the 1B/RF side regardless of batter hand (correct for LH, backwards for RH; as-built pooled pearson −0.04, L +0.22 / R −0.17). **Fixed**: added `ZONE_MIRROR` / `_mirror_positions` / `resolve_batter_hand`; `suggest_shift_type` and `default_positions_for_shift` now take `bats` and reflect the pull side about x=0.5 for RH; the service resolves batter hand (switch-hitters by pitcher hand) and threads it through `compute_alignment` / `score_custom_positions`; `bats=None` = prior behavior. 5 unit tests; 122 green. Re-run via shipped code: pooled pearson −0.04 → **+0.14**, per hand **L +0.22 / R +0.30 (both positive)** — direction validated (**PARTIAL PASS**). **Remaining**: the `infield_shift` template is a *gentle lean*, so predicted shift *magnitude* is under-predicted (slope +1.39) — a stronger template is the next lever if Part 2 needs it.
- **RAW `coverage`/`predicted_hit_pct` as a calibrated probability — RULED OUT (2026-09-02).** Reliability slope 0.37; the range model (27 ft/s league-average, linear decay, 400-ft normalization) under-covers, collapsing gap balls to P(out)≈0. Do not present the *raw* values as probabilities/expected outs. **Resolved by recalibration** (per-trajectory isotonic, slope→0.99) — but the fix is a not-yet-wired offline artifact; the API still returns raw `coverage`.

## Highest-value modeling note

Both P0 (evaluation) and the calibration fix are done; the coverage surface is a validated, calibrated probability at the standard alignment (modestly better than zone lookups). The next bottlenecks, in order: (1) **productization** — wire the persisted, versioned per-trajectory isotonic calibrator into the alignment service and relabel `predicted_hit_pct`; stop surfacing raw `coverage`. (2) **P1 prescriptive/counterfactual evaluation** — now unblocked. (3) **Range model** (`compute_reach`) — recalibration fixed the scale, not the physics; a better range model is the lever to widen the currently-modest margin over a zone×trajectory lookup; candidate cross-check vs ingested Statcast OAA (DATA_GAP_ANALYSIS Gap 5). Do not add spatial features (finer zones, carry physics, arm models) before P1 shows the geometry is the bottleneck. See `EXPERIMENTS.md`, `TRUST_REPORT.md`.
