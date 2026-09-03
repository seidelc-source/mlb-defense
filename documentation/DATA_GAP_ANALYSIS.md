# Data Gap Analysis

> Project-specific: what information is missing, what it would be worth, and how to get it. Re-run when the dominant uncertainty changes.

## Dominant uncertainty

**As of 2026-09-02, the dominant uncertainty has shifted.** The out-model gap is closed: an outcome-linked evaluation now exists (P0), and after per-trajectory recalibration the standard-alignment P(out) surface is validated (beats zone lookups, slope≈1). The new dominant uncertainty is **prescriptive**: does *moving fielders to the recommended alignment* improve realized outs? P1 (categorical shift decision) is designed and runnable now. But the engine's headline feature — **fine-grained x,y placement** — is **UNKNOWN and untestable with current data** because per-play fielder coordinates are not available (`fielder_positions` unpopulated; not in the ingested feed). This is now the binding data gap.

_Superseded (kept for history):_ the original dominant uncertainty was the absence of any outcome-linked evaluation of the raw `coverage`/`predicted_hit_pct`. Closed by P0 + recalibration (see EXPERIMENTS.md, MODELING.md). [VERIFIED]

## Gaps

| # | Missing information | Type | Blocks what | Candidate remedy |
|---|---|---|---|---|
| 1 | Realized batted-ball outcome (out/hit) linked to the **actual fielder alignment** in play | missing | Any accuracy claim; external baseline; calibration | Pull Statcast fields carrying alignment/shift context + outcome; join to `pitch_appearance` |
| 2 | An external, outcome-based baseline (league-average or actual-team positioning → out rate) | missing | Knowing if the heuristic beats "do nothing" | Aggregate realized out rates by scenario as a reference |
| 3 | Calibration of coordinate transforms (`hc_x/hc_y`→grid; 1 unit = 400 ft) against known landmarks | unreliable | Zone-assignment correctness; reach realism | Validate constants against a few known field coordinates (bases, wall distances) |
| 4 | Ground-truth landing-location density (vs. 8 hand-placed Gaussian zones) | **landing half RESOLVED 2026-09-03** | Was the binding defect for served absolute P(out) (+0.055 bias). Fixed: serving now uses per-batter empirical `hc_x/hc_y` histograms (bias +0.005). Residual finding: landing location carries no batter-level out signal — that signal lives in EV/trajectory composition (new P3 idea). Hit-mass/positioning half of the gap remains open (P2) | `services/alignment/landing.py` + `league_landing_v1.json` |
| 5 | Statcast OAA by fielder × direction as a check on the range/coverage model | unused | Whether reach radii are realistic | `fielding_profile.oaa_*` already ingested — compare implied vs. actual OAA |
| 6 | Meaning/label audit of `predicted_hit_pct` semantics for consumers | misaligned | Over-interpretation risk in the UI | RESOLVED (2026-09-02): per-trajectory isotonic calibrator fit, persisted (`out_calibrator_v1`), and wired — served values are calibrated P(hit)/P(out) with `calibrator_version` stamped |
| 7 | **Per-play fielder start (x,y) coordinates** | missing | Validating the engine's **fine placement**; a non-categorical prescriptive eval | Investigate Statcast player-tracking / fielder-alignment feeds (DATA_SOURCES candidate) |

## Candidate sources (ranked by expected decision impact per effort)

1. **Statcast alignment + outcome join (Gap 1/2)** — highest impact: unlocks all validation. Data likely already partially present (`hc_x/hc_y`, `events`, shift flags in some seasons). Moderate effort (join + outcome aggregation). See `DATA_SOURCES.md` "Realized … outcome" record.
2. **Existing ingested OAA as a range-model check (Gap 5)** — low effort (data already in `fielding_profile`), medium impact.
3. **Coordinate calibration (Gap 3)** — low effort, medium impact (protects target correctness).
4. **Empirical density from `hc_x/hc_y` (Gap 4)** — medium effort, medium impact; only pursue after Gap 1 shows zoning is the bottleneck.

## Recommendation

_Original recommendation (build the out-model eval harness) — DONE 2026-09-02 (P0 + recalibration); the surface is now measurable and validated at the standard alignment._

**Current highest-value action**: run **P1** (categorical shift-decision validation — designed, runnable on current data) to determine whether the engine's *recommendation* has prescriptive value. **Gated behind P1**: if the categorical shift recommendation validates (or fine placement is shown to be the specific bottleneck), pursue **Gap 7 — per-play fielder (x,y) coordinates**, the only path to validating the engine's fine-placement feature. Do not attempt to validate fine placement with a model-only counterfactual (circular). [INFERRED]
