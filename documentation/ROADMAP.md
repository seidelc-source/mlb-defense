# Roadmap

> Living plan — owned by `/ds-plan` (deliberate build/revise) and `/ds-next` (execute and amend). Two rules keep it honest: **detail decays with distance** (P0 concrete with acceptance criteria; P3 one-liners — never plan step 5 at step-1 resolution), and **every item carries kill criteria** ("would change if: <evidence>") so the plan stays adjustable instead of becoming a commitment. Log every change with its reason; move dead items to the graveyard — never silently delete.

## Direction

The descriptive question is answered: the engine's coverage surface, recalibrated per-trajectory, is a valid P(out | standard alignment) that modestly beats zone lookups (VERIFIED). The prescriptive question is half-answered: positioning direction is right after the handedness fix, shifting *broadly* beats always-standard, but the engine's pull-based shift-*selection* adds no value over "shift everyone" and fine x,y placement is untestable without fielder coordinates. This phase ships what is validated (the calibrator), stops shipping what isn't (raw probabilities, the selection heuristic as outcome-validated), and then pursues the two open levers: a shift-selection signal that captures the oracle's +33.5/1000 headroom, and the fielder-coordinate data that would unlock fine-placement validation.

## P0 — now (concrete, acceptance criteria required)

- [x] **DONE 2026-09-02 (commit `08d1c46`)** — Reproducibility floor: initial git commit + persist experiment artifacts out of `/tmp` — **why now**: the repo has ZERO commits and every VERIFIED result (P0 eval, recalibration, P1 Parts 1–2) is backed only by `/tmp/*.json` files and an untracked working tree — one reboot or stray edit and today's evidence is irreproducible; reproducibility sits above validation and production on the priority stack · **done when**: initial commit on `main` covering backend/frontend/documentation; experiment result JSONs + plots copied into a tracked `documentation/artifacts/` (or `backend/artifacts/`) with the EXPERIMENTS.md repro commands pointing at them; `.gitignore` excludes venv/node_modules/.env · **would change if**: — (no evidence makes version control optional).
- [ ] **Wire the per-trajectory isotonic calibrator into the alignment service** — **why now**: productionization of an already-validated artifact; the API still returns raw `coverage`, which is VERIFIED-miscalibrated (slope 0.37) — every UI number is currently wrong-scaled. Note the artifact does not exist yet — `eval_recalibrated.py` fits and discards it, so this item includes a fit-and-persist step (per-trajectory isotonic, full-data fit, versioned) before wiring · **done when**: persisted, versioned calibrator loaded by the service; `predicted_hit_pct` computed through it and relabeled/documented as a calibrated P(hit); raw `coverage` no longer surfaced as a probability; unit test pins calibrator version + a golden transform; smoke passes · **would change if**: re-fit on wiring-time data fails the reliability check (slope outside ~[0.9, 1.1]) → return to recalibration experiment before shipping.
- [ ] **Stop presenting the pull-based shift recommendation as outcome-validated** — **why now**: P1 Part 2 (VERIFIED) shows `suggest_shift_type` selection adds no value over shifting everyone; surfacing it as a validated recommendation is an over-claim · **done when**: API/UI copy and docs label the shift suggestion as heuristic/unvalidated (or the UI defaults to the per-batter optimized placement, which *is* direction-validated); TRUST_REPORT scope reflected in user-facing language · **would change if**: a new selection signal validates (see P1) — then re-label as validated.

## P1 — next (a sentence each)

- **Find a shift-selection signal with real value** (candidates: spray-profile dispersion, batted-ball speed mix, batter sprint speed, count/game-state) scored with the existing within-batter policy-value estimator — why: oracle selection shows +33.5/1000 headroom over shift-everyone that pull-concentration doesn't capture · would change if: 2–3 candidate signals also show monotone-declining V(τ) → accept "shift broadly" as the policy and kill per-batter selection (decision point A).
- **Cross-check `compute_reach` against ingested Statcast OAA** (Gap 5 — data already in `fielding_profile`) — why: recalibration fixed the scale, not the physics; a realistic range model is the lever to widen the modest ~0.012 log-loss margin over zone×trajectory · would change if: implied-vs-actual OAA shows the current radii are already unbiased → deprioritize range-model work.
- **Calibrate coordinate transforms against known landmarks** (Gap 3: `hc_x/hc_y`→grid, 1 unit = 400 ft, bases/wall distances) — why: low effort, protects target correctness for everything downstream · would change if: —(cheap enough to just do).

## P2 — later (one-liners)

- Acquire per-play fielder start (x,y) coordinates (Gap 7 — Statcast player-tracking/alignment feeds) to validate fine placement · would change if: no feasible public source after a scoped search → cap the app's claims at categorical/direction-level and park permanently.
- Replace/tune the 8-Gaussian spray zones with empirical `hc_x/hc_y` landing density (Gap 4) · would change if: P1 range-model work shows geometry, not zoning, is the binding error source.
- Point-in-time-honest profile lookup for retrospective analyses (as-of-date fielding profile + pre-scenario spray) · would change if: no further backtests are planned.

## P3 — someday / parked

- Arm-strength / double-play modeling in the out conversion.
- Weather-effect validation (carry/drift factors are hand-set, never outcome-checked).
- FanGraphs xFIP/SIERA pull for `PitcherProfile` (fields reserved, NULL).
- Calibrated uncertainty replacing the `0.30 + n/400` confidence heuristic.

## Decision points

- **A (shift policy)**: if no candidate selection signal beats shift-everyone under the policy-value estimator → the product recommendation becomes "shift broadly (where legal-era-relevant), skip per-batter selection"; per-batter selection moves to graveyard. If one validates → wire it into `suggest_shift_type` and re-label as outcome-validated.
- **B (fine placement)**: if fielder-coordinate data (Gap 7) is acquirable → run the non-circular fine-placement eval; the engine's headline x,y feature gets a verdict. If not → the trust ceiling for fine placement stays UNKNOWN and UI claims must stay categorical.
- **C (range model)**: if OAA cross-check (P1) shows reach radii are materially biased → invest in `compute_reach` re-derivation; else accept the modest margin and stop geometry work.

## Change log (newest first)

- 2026-09-02 (later, /ds-plan revision) — Added a leading P0 reproducibility item: verified in-code that no persisted calibrator exists (fit-and-discarded inside `scripts/eval_recalibrated.py`; service still returns raw `predicted_hit_pct`, `engine.py:512`), and found that the repo has zero git commits with all experiment artifacts in `/tmp` — reproducibility gates the other P0s on the priority stack. Calibrator-wiring acceptance criteria now note the artifact must be *created* (fit + persisted), not just loaded. No other structural changes; P1–P3, decision points, and graveyard unchanged.
- 2026-09-02 — Initial roadmap at (re-)integration. Reflects state after P0 outcome eval, recalibration PASS, handedness fix, and P1 Parts 1–2: P0 = ship the calibrator + stop over-claiming the shift selection; P1 = selection signal, OAA range check, coordinate calibration; P2 gated on Gap 7 data.

## Graveyard (killed ideas — prevents re-litigating them)

- **Stronger static `infield_shift` template** — killed 2026-09-02: maximally-aggressive-but-legal template vacated the up-the-middle lane; predicted lift went negative. Magnitude belongs to per-batter `optimize_positions`, not a fixed template. [EXPERIMENTS.md]
- **Cross-batter correlation as the lens for judging the optimizer** — killed 2026-09-02: an optimizer tautologically predicts ≥0 benefit for every batter, so per-batter predicted-vs-realized correlation cannot rank it; replaced by the within-batter policy-value estimator. [TRUST_REPORT.md]
- **Pull-concentration as the shift-selection signal** — killed 2026-09-02 (P1 Part 2): V(τ) declines monotonically with selectivity; most-pull batters are not disproportionately the beneficiaries. Selection *value* exists (oracle +33.5/1000) but this signal doesn't capture it. [EXPERIMENTS.md]
