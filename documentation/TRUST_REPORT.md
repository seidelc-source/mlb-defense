# Trust Report

> Project-specific: can current results be believed, and for what purpose? Updated by trust gates and reviews. Newest assessment first; keep prior assessments below as history.

## 2026-09-09 assessment (angular ground model validated offline — RH path to recovery identified)

**Update on the assessment below**: the diagnosis chain (ablation → depth culprit → geometry re-derivation) concluded the same day. A bearing-only angular-corridor ground model (league-level infielder stations, isotonic angular decay, zero free parameters) **recovers direction for both hands on the held-out Part 1 harness: L +0.335 / R +0.228** — passing its pre-registered bars. The SERVED system is unchanged (still LH-only validated) until the pre-registered shipping experiment integrates the model with full gates; the angular model's absolute delta level is biased (ranking validated, level not — calibration at shipping). Guardrail investigation also produced a scope correction for the descriptive claims: **grounder fielded-cells encode the outcome** (out rate 85.5% in infield zones vs 0.7% in outfield zones), so every cell-conditioned descriptive comparison on grounders — the engine surface AND the zone baselines, including this section's "zone×traj now edges the engine" — is partially tautological on its ground component; it remains a legitimate descriptive estimand but is NOT evidence of prescriptive ranking power in either direction. [VERIFIED — EXPERIMENTS.md 2026-09-09]

## 2026-09-09 assessment (frame revalidation — DOWNGRADES: RH direction regressed, zone×traj baseline now competitive)

**Finding**: the pre-registered frame revalidation (EXPERIMENTS.md 2026-09-09) fired BOTH stop conditions. (1) **Direction**: in the corrected frame the handedness-aware template's predicted-vs-realized shift lift is L **+0.35** (stronger than the old +0.22) but **R −0.00** (was +0.30). Diagnostics localize the collapse to the predicted side (realized outcomes bit-identical), and the old-frame RH predictions still predict realized lift (+0.34) — i.e., the rebuild's interaction with the RH/mirrored geometry **destroyed a real signal** (frame-interaction defect, mechanism under investigation), it did not merely expose an artifact. (2) **Descriptive**: the corrected-frame zone×trajectory lookup improved to log loss 0.5252 and now **slightly beats the calibrated engine surface (0.5283)**; the engine keeps only a thin AUC edge (+0.007 vs zone×traj; +0.0375 CI-separated vs plain zone). [VERIFIED]

**Trust consequences (downgrades, effective immediately)**: `oaa_delta` direction is **TRUSTED for LH batters only**; for RH it is **NOT validated in the served frame** (UI/API language updated). The descriptive claim is now "ranks outs better than a plain zone lookup (CI-separated); does NOT beat a zone×trajectory lookup with separation." The calibrated P(out) level/reliability gates are unaffected (they re-passed at the rebuild). The v1 frame is not restored — its geometry is measurably wrong; the fix target is the new frame's engine interaction. **No further modeling until the RH defect is diagnosed** (top roadmap item, pre-registered ablation).

## 2026-09-04 assessment (frame rebuild shipped — coordinate distortion RESOLVED)

**Update on the assessment below**: the coordinated rebuild shipped the same day, all pre-registered gates passing (EXPERIMENTS.md 2026-09-04 frame-rebuild entry): era-aware canonical transform, zones backfilled (24.3% changed), sprays rebuilt, landing v2, calibrator v2 (LOSO slope 0.995), served level bias +0.0049, serving `0.4.0+cal-v2`. The ball frame, fielder frame, park geometry, and UI displays now share one measured coordinate system; the geometry distortions listed below are resolved. Two observations: (1) the calibration map's dynamic range widened (more discriminative surface — ground g now spans 0.32–0.94); (2) per-batter served-vs-realized correlation flipped −0.10 → +0.095 (split-half +0.05) — directionally encouraging but weak; **the permanent cap on absolute-probability claims is unchanged**. Foul-territory balls (~2.3%) now honestly clip to the field edge instead of being silently misplaced inside fair ground. [VERIFIED]

## 2026-09-04 assessment (coordinate frame materially miscalibrated — in-frame claims stand, geometry distorted)

**Finding**: the pre-registered hc-transform calibration (EXPERIMENTS.md 2026-09-04) shows the canonical ball-coordinate transform is materially wrong: true scale 2.29 ft/hc-unit vs assumed 2.0 (CI [2.284, 2.297]), home offset 6.1 units, with era drift (2.22 → 2.37 across MLBAM's raster change). The ball frame is radially compressed ~13% relative to the fielder frame (−16 ft at 2B, −42 ft at a 330-ft wall). [VERIFIED — `documentation/artifacts/hc_transform_calibration.json`]

**Trust consequences — read carefully, this is NOT a retraction**: every outcome-validated result (calibrator + LOSO gate, landing density, policy evals) computed balls and coverage in the SAME frame, and the isotonic calibrator absorbs frame scale in the coverage→P(out) map — so served probabilities and `oaa_delta` direction claims **stand as validated-in-frame**. What IS distorted: (1) the fielder-reach ↔ ball-cloud interaction (reach radii in true feet act on a compressed ball cloud → effective coverage overstated ~13% radially, non-uniformly with depth); (2) geometry displays — `depth_ft`, spray overlays vs park walls (1.0 = 400 ft) misplace balls up to ~50 ft at wall depth; (3) weather drift/carry magnitudes operate on compressed distances. Remediation: the **coordinated frame rebuild** is the top roadmap item — transform + zones + sprays + landing artifacts + calibrator refit (gate must re-pass) + eval re-runs + demo fixtures, moved together; never piecemeal.

## 2026-09-04 assessment (reach model vs OAA — D5 partially resolved, split verdict)

**Finding**: the pre-registered reach-vs-OAA cross-check (EXPERIMENTS.md 2026-09-04) tested TRUST_REPORT threat D5 (roster-attribute-driven P(out) deltas unvalidated) at the player level, against Savant per-opportunity OAA rates 2016–2025. **Split verdict**: OF sprint-speed reach VALIDATES for ranking (Spearman +0.33, CI [+0.24, +0.41]) but is under-credited ~2× (slope 1.95); **IF reach is noise** (Spearman +0.05 CI spans 0; slope 0.036) — the engine moves served P(out) on infielder speed with essentially no realized counterpart. [VERIFIED — `documentation/artifacts/reach_vs_oaa.json`]

**Trust consequences**: (1) cross-roster comparisons and roster-attribute effects on served P(out) are **partially trusted for OF, untrusted for IF**; (2) **injury degradation on infielders** multiplies sprint speed → its served P(out) impact has no validated basis (UI already labels absolutes as league-scale, which contains the damage); (3) within-request `oaa_delta` (same 7 fielders both arms) is largely insulated — attribute scale mostly cancels. Underlying data defects recorded in DATA_KNOWLEDGE: reaction/route all NULL, innings/games all 0, per-opportunity rates dropped by ingest. Remediation is roadmapped (IF reach re-derivation, pre-registered; leaderboard ingest fix).

## 2026-09-04 assessment (shift-selection question CLOSED — decision point A fired)

**Finding**: the pre-registered 3-signal experiment (EXPERIMENTS.md 2026-09-03, run 23:59) falsified the last roadmap candidates for a per-batter shift-selection signal: spray dispersion, hard-grounder share, and batter sprint speed all fail to beat "shift everyone" under the within-batter policy-value estimator (best Δs −0.5 to −1.2/1000, all CIs span 0, era-half guardrail fails). Combined with Part 2's pull-concentration failure, four observable signals spanning spray location, contact quality, and batter speed now show the same monotone-declining V(τ). The +13.9/1000 "oracle headroom" is reinterpreted as mostly estimation noise (in-sample max of two noisy per-batter arm rates). [VERIFIED — `documentation/artifacts/shift_selection_signals.json`]

**Trust consequences**: the shift-*selection* question moves from "not validated, open" to **CLOSED — selection is untrusted and retired** (ROADMAP graveyard; decision point A resolved). The trusted product policy is "shift broadly": surface the per-batter optimized placement (direction-validated) for every batter; `suggest_shift_type` is a template label only, already presented as such in UI/API copy. Everything else is unchanged: calibrated per-ball P(out | standard) surface TRUSTED (descriptive), `oaa_delta` direction TRUSTED, absolute probabilities population-level only (capped), fine x,y placement UNKNOWN (Gap 7).

## 2026-09-03 assessment (empirical landing density shipped — level repaired, batter-signal question closed)

**Update on the assessment below**: the P1 fix ran the same day. Serving (0.3.0) now aggregates under the batter's empirical `hc_x/hc_y` landing density with league-prior shrinkage (`services/alignment/landing.py`); the uniform-fallback bug (D1) and the `np.roll` weather wrap (D3) are fixed. Pre-registered re-run (EXPERIMENTS.md 2026-09-03 empirical-density entry): **level bias +0.0052 — PASS**; **batter-level signal — the kill criterion fired** (pearson −0.10, robust to the split-half guard). Decision per the pre-registered ROADMAP criterion: **absolute-probability claims capped permanently at population level**; batter ranking on served P(out) is forbidden in the schema docs; the product's decision quantity is `oaa_delta` (direction-validated). A deviation is disclosed in EXPERIMENTS.md: the eval script's stricter slope bar technically read FAIL, but it was ill-conditioned at near-zero served spread and its revert action was dominated — the roadmap criterion governs. [VERIFIED]

**What this buys**: served absolutes are now honest at the level they claim (population-anchored, +0.005); the open "can the aggregation carry batter signal?" question is **answered — no, not via landing location** (slightly anti-informative; hypothesized EV/composition confound, recorded as the future path: LD/FB/PU split + exit-velocity-aware calibration). 149 tests green; smoke passes; live payload stamps `landing_source` and `model_version=0.3.0+cal-v1`.

## 2026-09-03 assessment (ds-review + red-team of `calibrated_out_probability` — served ABSOLUTE probabilities NOT calibrated)

**Finding**: the 2026-09-02 wiring's serving aggregation was adversarially reviewed (scientific-red-team) and then outcome-tested end-to-end (`scripts/eval_served_aggregation.py`, 884k standard-alignment balls). **The served absolute `predicted_out_pct`/`predicted_hit_pct` are NOT calibrated**: level bias **+0.0546** (mean served 0.7448 vs realized 0.6901) and **zero cross-batter signal** (reliability slope −0.14, AUC 0.498, per-batter pearson +0.02). The per-ball map g(coverage→P(out)) remains VERIFIED (that validation is untouched); the defect is taking its expectation under the unvalidated 8-Gaussian landing density, which concentrates mass at high-coverage zone centers while ~half of real balls land at coverage≈0. [VERIFIED]

**Additional red-team findings**: (D1) the no-spray uniform fallback serves 0.618 under the calibrated label — biased −0.07, the opposite direction [VERIFIED]; (D3) weather `np.roll` wraps grid mass around edges (up to ~17% of air mass under extreme carry) — minor for P(out), corrupts optimizer inputs under extreme weather [VERIFIED]; (D4) served fields don't state the HR-excluded estimand [VERIFIED]; (D5) applying g off-standard-alignment / off-league-average reaches rests only on the transfer check (roster attributes alone move served P(out) +0.04, unvalidated) [VERIFIED at code level]. Attacks that FAILED: coordinate-frame mismatch (frames are identical), mix-share blowup (bounded), serving-path fidelity (exact), OOF discipline of g (clean).

**Trust consequences**: the 2026-09-02 assessment's "product honesty upgraded" claim was premature for the **absolute** probabilities — they must not be labeled calibrated until the aggregation is fixed (candidate fixes in EXPERIMENTS.md 2026-09-03: relabel now; level anchor; or the principled fix, per-batter empirical landing density — Gap 4). What remains trustworthy: the per-ball calibrated surface (descriptive claim, unchanged), `oaa_delta` **direction** (P1 Part 1), the wiring mechanics (artifact, versioning, tests). The shift-selection heuristic and fine placement remain untrusted as before.

**Remediation applied same day (user decision)**: option (a) — all claim surfaces relabeled (schemas, engine docstrings, frontend types, CLAUDE.md): `oaa_delta` = direction-validated calibrated delta; absolute `hit_pct`/`out_pct` = uncalibrated probability-scaled indexes (~+0.05 high, HR-excluded estimand). Option (c) promoted to ROADMAP P1; D1 (no-spray fallback) and D3 (np.roll wrap) queued as P1 bugfixes.

## 2026-09-02 assessment (calibrator wired into the service — productization gap closed)

**Update**: the per-trajectory isotonic calibrator now SHIPS. `scripts/fit_calibrator.py` re-ran the pre-registered reliability gate on fit-time data (LOSO OOF slope **0.992**, within [0.9, 1.1] → the kill criterion did not fire), fit final maps on all 884,402 standard-alignment balls (2016–2025), and persisted a versioned artifact (`out_calibrator_v1.json`, tracked in git, exact sklearn↔serving round-trip). The alignment service applies it end-to-end: `predicted_hit_pct`/`predicted_out_pct`/`predicted_oaa_delta` are now calibrated per-ball probabilities — per-cell coverage mapped through the calibrator, averaged under the batter's **landing** density (not the hit-weighted grid, which would bias the expectation), blended by the batter's ground/air mix with pitcher tilt. Raw `coverage` is no longer surfaced as a probability anywhere; responses carry `calibrator_version=v1`, logged recommendations carry `model_version=0.2.0+cal-v1`, and cache keys include the model version so no stale raw-scale numbers are served. Verified: 138 unit/integration tests green (16 new, incl. pinned golden transforms), end-to-end smoke passes, live response P(out)=0.757 at realistic scale. [VERIFIED]

**Scope caveats (unchanged in kind)**: the calibration is validated at the standard alignment with league-average fielders; applying it to candidate alignments rests on the transfer check (std-fit map stayed calibrated on shifted balls, slope 0.97 — reassuring, not conclusive). The trajectory-mix blend (batter ground share × pitcher tilt) is a reasonable-but-unvalidated aggregation layer on top of the validated per-trajectory maps. The shift-selection heuristic and fine x,y placement remain exactly as untrusted as the previous assessment states.

**Net trust status**: unchanged in scope, upgraded in **product honesty** — what the API now shows matches what was validated. Remaining P0: user-facing copy still presents the shift suggestion without an "unvalidated heuristic" label.

## 2026-09-02 assessment (after P1 Part 1 handedness bug — FIXED & validated)

**Update**: the handedness bug below was **fixed** in `services/alignment/engine.py` (handedness-aware `suggest_shift_type` / `default_positions_for_shift`; service resolves batter hand, switch-hitters by pitcher hand; `bats=None` preserves prior behavior; 5 unit tests; 122 green). Re-running P1 Part 1 through the shipped code: predicted-vs-realized shift-lift pearson **−0.04 → +0.14** pooled, **L +0.22 / R +0.30 (both positive)** — the shift recommendation now tracks realized benefit in **direction** for both hands.

**Further (2026-09-02)**: a stronger static template was tried and **rejected** (created up-the-middle gaps); Part 1 was then re-scoped to the engine's **per-batter optimized** recommendation (`optimize_positions`). Finding: optimization **fixes magnitude** (mean predicted lift +0.049 ≈ realized +0.025; the template gave ~0) and needs no handedness flag, but **loses per-batter discrimination** (cross-batter pearson +0.02 — an optimizer tautologically predicts ≥0 benefit for every batter, so this correlation was the wrong lens). So per-batter curation is the right *mechanism* (correct direction, realistic magnitude).

**Part 2 (off-policy shift-decision value, 2026-09-02)**: within-batter policy-value estimator (both arms observed; no coverage model → no circularity). Shifting **broadly** beats always-standard (+19.7/1000 balls, CI [+12.5,+26.5]; quasi-experimental, era-specific), but the engine's **pull-concentration shift-SELECTION adds no value over "shift everyone"** — V(τ) declines monotonically as you get selective, so the most-pull batters aren't disproportionately the beneficiaries. Oracle selection (+33.5/1000, in-sample/optimistic) shows selection value exists but pull-concentration doesn't capture it.

**Net trust status**: the engine's **calibrated per-ball out-probability** (recalibration PASS) and **correctly-aimed per-batter positioning** (handedness fix) are trustworthy; its **shift/no-shift DECISION heuristic** (`suggest_shift_type`, pull-based) is **NOT validated** as adding value over shifting broadly — do not surface it as an outcome-validated recommendation. Fine-placement validation still gated on fielder-coordinate data (Gap 7).

## 2026-09-02 assessment (after P1 Part 1 — handedness bug found)

**Overall status**: CONDITIONALLY TRUSTED for the *descriptive* calibrated out-surface (unchanged); the **prescriptive shift recommendation is NOT trusted** — P1 Part 1 shows the engine as-built does not track realized shift benefit, due to a verified handedness bug. _[Superseded by the fix above.]_

**Scope**: the engine's infield shift/no-shift *recommendation*, validated against realized out-rate lift on 299k ground balls (2016–2022, 344 batters). See `EXPERIMENTS.md` P1 Part 1.

### What we now know
- **Engine shift recommendation NOT prescriptively valid as built** (VERIFIED): predicted vs realized shift lift pearson −0.04, sign-agreement 0.46. [EXPERIMENTS.md]
- **Root cause — handedness bug (VERIFIED at code level)**: `services/alignment/engine.py` hardcodes "pull" to the 1B/RF side (`pull_zones={1,2}`) and shades the `infield_shift` template toward 1B regardless of batter hand; no `bats`/mirror logic exists in `services/alignment/`. Correct for LH pull hitters (pearson +0.22), backwards for RH (pearson −0.17). Also means RH pull hitters are rarely flagged for a shift at all.
- **Out-model not hopeless once aimed right** (INFERRED, weak): handedness-corrected predicted lift positively but weakly tracks realized (pearson +0.14); magnitude under-predicted because the engine "shift" is a gentle lean, not a real shift.

### Blocking issues (P0/P1)
1. **Fix the handedness bug** in `suggest_shift_type` (pull/oppo zones) and `default_positions_for_shift` (mirror by batter hand; handle switch-hitters by pitcher hand), then re-run P1 Part 1. **Parts 2–3 are gated on this.**
2. (carried) Wire the recalibration artifact before surfacing `predicted_hit_pct` as a probability.

### Residual uncertainty
Whether a handedness-corrected engine's shift recommendation is prescriptively valid is UNKNOWN pending the fix + re-run. Fine x,y placement remains UNKNOWN (data gap).

---

## 2026-09-02 assessment (after recalibration experiment — PASS)

**Overall status**: **CONDITIONALLY TRUSTED** (calibrated out-probability surface at the standard alignment). Upgraded from EXPLORATORY because the P0 blocker (no valid probability) is resolved: a per-trajectory, out-of-fold isotonic recalibration of `coverage` beats the zone baselines on log loss/Brier with CI separation and reliability slope ≈ 1 (see `EXPERIMENTS.md`, 2026-09-02 recalibration entry).

**Scope**: `P(out | standard alignment)` only, for a *calibrated* surface. Does NOT cover the prescriptive `oaa_delta` (P1, now unblocked but not yet run) or the currently-shipped raw `coverage`/`predicted_hit_pct`, which remain miscalibrated until the calibrator is wired in.

### What we now know (VERIFIED)
- **Calibrated coverage is a valid, slightly-better-than-baseline probability model.** Isotonic per-trajectory: log loss 0.582 vs zone 0.607 (Δ −0.025, CI [−0.0257, −0.0244]) and vs zone_traj 0.594 (Δ −0.012, CI [−0.0127, −0.0110]); slope 0.99; AUC 0.656. The margin over zone lookups is **real but modest**.
- **The raw engine output is still not a probability** — `predicted_hit_pct`/`oaa_delta` as currently computed remain miscalibrated (slope 0.39). They must not be surfaced as probabilities until the calibrator ships.
- **Transfer check**: the standard-fit map stayed calibrated on shifted-alignment balls (slope 0.97) — reassuring, with the categorical-alignment / standard-position caveat.

### Blocking issues (P0)
- None for the *evaluated* (calibrated, standard-alignment) surface. The remaining gap is productization: the calibrator is an offline artifact, not yet wired into the service.

### Material risks (P1/P2)
- **P1 — Prescriptive `oaa_delta` still unvalidated** (counterfactual). Now unblocked; but note the modest margin of the fine geometry over zone lookups — P1 should weigh the range-model fix against the geometry's value.
- **P1 — Productization gap**: raw `coverage` is still what the API returns. Wiring the persisted, versioned per-trajectory calibrator into the alignment service and relabeling `predicted_hit_pct` is required before any UI presents these as probabilities.
- **P2 — Range-model realism**: recalibration corrects the *scale* but the underlying `compute_reach`/coverage decay is still physically crude; a better range model could widen the (currently modest) margin. Candidate cross-check vs ingested Statcast OAA (DATA_GAP_ANALYSIS Gap 5).

### Recommended remediation (ordered)
1. Wire the per-trajectory isotonic calibrator (persisted, versioned) into the alignment service; relabel `predicted_hit_pct`; stop surfacing raw `coverage` as a probability.
2. Run the P1 prescriptive/counterfactual evaluation on the calibrated surface.
3. Revisit the range model (`compute_reach`) to try to widen the margin over zone lookups.

### Residual uncertainty
Whether better *positioning* improves realized outs (prescriptive) is still UNKNOWN — P1. Whether the fine geometry is worth more than a well-calibrated zone×trajectory lookup is now known to be "yes, but modestly."

---

## 2026-09-02 assessment (after P0 out-model evaluation)

**Overall status**: EXPLORATORY (unchanged) — but the central uncertainty is now **measured**, and the P1 "`predicted_hit_pct` semantics" risk is **confirmed, with a specific fix**.

**Scope**: The engine's per-location out-probability surface at the standard alignment, evaluated on **884,402** standard-alignment in-play batted balls (**2016–2025**, LOSO). Result stable across the heavy-shift era and the post-ban era. See `EXPERIMENTS.md` (2026-09-01 entry, RUN 2026-09-02) for full numbers.

### What we now know (VERIFIED)
- **The coverage surface has real spatial signal**: it ranks outs-vs-hits better than an 8-zone (and zone×trajectory) lookup — Δ AUC +0.056, 95% CI [+0.053, +0.058], stable across all five seasons. The geometry is *not* worthless.
- **The coverage surface is not a probability**: reliability slope 0.369, intercept 0.627; ~half of all batted balls receive P(out)≈0 from the engine while ~59% of them are actually outs. `predicted_hit_pct = 1 − Σ hit_prob × coverage` and `predicted_oaa_delta` therefore **must not be presented as probabilities or expected-out counts** — this closes the prior P1 "semantics mislabel" as CONFIRMED.
- **Root cause (INFERRED)**: the range/coverage model (league-average 27 ft/s, linear catch decay, single 400-ft normalization) covers too little area at high probability, collapsing gap balls to ~0.

### Blocking issues (P0)
1. **Recalibration required before any probability claim.** Fit an out-of-fold monotonic calibration (isotonic/Platt) `coverage → P(out)`; re-evaluate. Until then, UI numbers are directional at best. (Was: "no outcome-linked evaluation" — that P0 is now DONE; this is its successor.)

### Material risks (P1/P2)
- **P1 — Prescriptive `oaa_delta` still unvalidated** (counterfactual). Recommendation *ranking* may survive recalibration (monotone-preserving), but magnitudes do not. P1 counterfactual eval remains gated on a calibrated surface.
- **P2 — Range-model realism**: the miscalibration points directly at `compute_reach`/coverage decay as the thing to fix or re-derive (candidate check against ingested Statcast OAA — DATA_GAP_ANALYSIS Gap 5).
- **P2 — Pre/post-2023 "Standard" semantics differ**; per-season LOSO showed the result is stable regardless, so this did not bite here.

### Recommended remediation (ordered)
1. Recalibrate `coverage → P(out)` out-of-fold; re-run the harness; relabel `predicted_hit_pct` in API/UI accordingly.
2. Revisit the range model (position-specific reach, non-linear decay) — the miscalibration is a coverage-area problem, not a coordinate problem.
3. Only then attempt the P1 prescriptive/counterfactual evaluation.

### Residual uncertainty
Whether a recalibrated surface beats the zone baseline on log loss/Brier (it beats on AUC already) is UNKNOWN until the recalibration experiment runs. Whether better positioning improves *realized* outs (prescriptive) remains UNKNOWN.

---

## 2026-09-01 assessment (initial, at Principal DS integration)

**Overall status**: EXPLORATORY

**Scope**: The alignment engine's outputs — `predicted_oaa_delta`, `predicted_hit_pct`, `confidence`, and the recommended top-N alignments — for the live `POST /api/v1/alignments/recommend` path and `score_custom`.

### Evidence for the status
- The engine is a deterministic, internally-consistent heuristic that respects MLB 2023+ shift legality and park fences (VERIFIED by `tests/unit/test_alignment_engine.py`).
- No test, script, or analysis compares any engine output to a realized defensive outcome or an external baseline (VERIFIED — grep of `tests/` shows only mechanical assertions; no backtest/accuracy code exists).
- Therefore the system is trustworthy as a **legal, plausible positioning suggestion tool**, and **not** trustworthy as a predictor of actual out conversion. Numbers must not be presented as validated OAA or hit probabilities.

### Blocking issues (P0)
1. **No outcome-linked evaluation.** `predicted_oaa_delta` is defined only against the engine's own "standard" alignment; it has never been checked against reality. No accuracy claim can be made. → Build the evaluation harness (see DATA_GAP_ANALYSIS Gap 1/2).

### Material risks (P1/P2)
- **P1 — Output-semantics mislabel**: `predicted_hit_pct = 1 − expected_outs`, where `expected_outs` is a covered fraction of *normalized* hit-mass, not an out probability. Consumers may read it as a real hit rate. Relabel/document or calibrate.
- **P1 — Coordinate calibration unverified**: `_fielding_zone_from_hc` uses a self-described "rough" normalization with magic constants; a systematic offset would misassign fielding zones and corrupt the spray distribution.
- **P2 — Coarse spatial resolution**: only 8 hand-placed Gaussian zones; centers/sigmas untuned against empirical landing density.
- **P2 — Range model simplifications**: single 400-ft normalization, outfielder sprint model applied to infielders, linear catch decay, no arm/DP modeling; default sprint 27 ft/s substitutes for missing data.
- **P2 — Confidence is not calibrated**: `0.30 + sample_n/400` is a sample-size proxy, not an uncertainty interval.

### Leakage / point-in-time findings
- **Live use**: leakage-free by construction (present-time inputs).
- **Retrospective use (if attempted)**: (a) `get_latest_profile` returns newest fielding profile → future data for past scenarios; (b) season-aggregate spray for season S contains the season-S outcome → target leakage. Any backtest MUST filter to pre-scenario information. [INFERRED]

### Validation findings
- Mechanical/implementation tests pass and are reasonable. No predictive validation exists. [VERIFIED]

### Data quality findings
- `general_result` uses a substring `"out" in events` fallback (over-broad) and drops unmapped events (silent under-count). `ball_trajectory` maps only 4 `bb_type` values. See DATA_KNOWLEDGE. [VERIFIED]

### Recommended remediation (ordered)
1. Build a point-in-time-honest evaluation harness with an external baseline (P0).
2. Calibrate/verify coordinate transforms (P1).
3. Clarify/relabel `predicted_hit_pct` semantics (P1).
4. Only then consider finer zoning / richer physics / arm modeling (deferred until evaluation justifies it).

### Residual uncertainty
Whether the heuristic's recommendations improve real out conversion over standard/actual alignments is currently **UNKNOWN** — not negative, just unmeasured.
