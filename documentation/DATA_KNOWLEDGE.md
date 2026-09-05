# Data Knowledge

> Project-specific knowledge: what has been learned about this project's data. One entry per dataset/table. Label claims: VERIFIED / INFERRED / ASSUMED / HYPOTHESIS / UNKNOWN. Record defects even after they are fixed — the history prevents re-litigating them.

## `pitch_appearance` (raw fact table)

- **Grain**: one row per pitch. [VERIFIED]
- **Keys & uniqueness**: `mlb_play_id` is the dedupe key; re-ingest is idempotent. [VERIFIED — CLAUDE.md, ingest]
- **Coverage**: 2016–2025 loaded per project convention; ~700k–750k rows per full season. [INFERRED — data_models.md]
- **Update/revision behavior**: nightly `statcast_nightly` ingests yesterday's pitches; Statcast values can be revised upstream — revision handling not verified. [ASSUMED]
- **Missingness & sentinels**: `hc_x/hc_y`, `launch_angle`, `bb_type`, `events` can be null (non-batted-ball pitches, missing tracking). Derived fields return None when inputs missing. [VERIFIED — `ingest_services.py`]
- **Prediction-time availability / lag**: available post-play; nightly lag for batch. [INFERRED]
- **Known quirks & defects**:
  - `fielding_zone` derived via `_fielding_zone_from_hc` = nearest of 8 hand-placed `ZONE_CENTERS` after a **"rough normalization"** (`nx=(hc_x-25)/200`, `ny=1-(hc_y)/200`). **CALIBRATED 2026-09-04 — materially wrong**: fitted vs 200k measured hit distances, true scale is **2.29 ft/hc-unit** (not the assumed 2.0; 14.5% error), home at (125.95, 206.0) not (125, 200), and the scale **drifts by era** (2.22 in 2016–2020 vs 2.37 in 2021–2025 — MLBAM raster change). Ball frame was radially compressed ~13% vs the fielder frame (−42 ft at a 330-ft wall). Also: `hit_distance_sc` is contaminated by roll for line drives (residual MAD 21.6 ft vs 7.7 for flies) and for grounders measures contact/bounce (~33 ft avg) while grounder `hc` marks the FIELDED location — the two are semantically different points. **REBUILT 2026-09-04**: canonical era-aware transform (`services/alignment/landing.hc_to_norm`, per-era fitted constants, pinned by `tests/unit/test_hc_transform.py`) shipped with the coordinated rebuild — zones backfilled (24.3% of assignments changed), sprays/landing/calibrator rebuilt (all gates passed), serving `0.4.0+cal-v2`. Frame caveat that remains BY CONSTRUCTION: foul-territory plays (~2.3% of in-play balls — behind-home popups, foul-line outs) clip to the fair-field edge; the old frame misplaced them inside fair ground. [VERIFIED — EXPERIMENTS.md 2026-09-04 entries]
  - `general_result` maps a hardcoded events set + a fallback `"out" in events` substring test → any unlisted event containing "out" is bucketed as out; unmapped events return None (dropped). [VERIFIED]
  - `ball_trajectory` only maps 4 `bb_type` values; anything else → None. [VERIFIED]
- **Join notes**: `pitcher_id → player.throws` (outer join) supplies pitcher handedness in spray aggregation; batters/pitchers with missing player rows lose hand scenario. [VERIFIED]

## `batter_spray_profile` (nightly aggregate)

- **Grain**: one row per (player, season, scenario, fielding_zone); scenario = (pitch_type, pitcher_hand, speed_band), all-NULL = "all". [VERIFIED]
- **Keys & uniqueness**: rebuilt via full `DELETE` then re-insert per season (`SprayAggregateService.aggregate`). [VERIFIED]
- **Coverage**: per-scenario rows only written above `MIN_COMBO_SAMPLE = 10` batted balls; the "all" aggregate always written. Only zones with `total>0` produce rows. [VERIFIED]
- **Rates**: `hit_pct`, `out_pct`, trajectory %s, specific-result %s = counts / total_batted_balls. Counts are honest raw sums. [VERIFIED]
- **Cross-season blend**: `season=None`/`season=0` collapsed by `spray_blend.merge_zone_rows` — counts stay raw sums; rates recency-weighted by `decay**(latest−season)` (`spray_recency_decay`≈0.72). [VERIFIED — CLAUDE.md, spray_blend.py]
- **Prediction-time availability**: season-S aggregate contains all of season S → **includes the outcome for any within-season retrospective prediction** (leakage risk if backtested). [INFERRED]
- **Known quirks**: hit-probability weighting in the engine uses `hit_pct * sample_n` per zone; only 8 zones exist so spatial resolution is coarse. [VERIFIED]

## `fielding_profile`

- **Grain**: one row per (player, season, position). [VERIFIED]
- **Fields**: `outs_above_average` (+directional), `fielding_run_value`, `sprint_speed_ft_s`, `reaction_time_s`, `route_efficiency_pct`, `arm_*`, catcher-specific. Synced weekly (`fielding_weekly`) for current season. [VERIFIED — data_models.md]
- **Engine use**: `get_latest_profile` returns the newest profile per fielder → for historical scenarios this is **future data** (lookahead). Fine for live use. [INFERRED]
- **Missingness**: engine `compute_reach` falls back to defaults (speed 27 ft/s, rt 0.4, route 85%) when attributes are null. [VERIFIED]
- **Defects found 2026-09-04 (reach-vs-OAA experiment)** [VERIFIED — SQL counts + ingest code + leaderboard probe]:
  - `reaction_time_s` and `route_efficiency_pct` are NULL for **all** rows → every fielder gets the defaults; cross-player reach variation is sprint-speed-only as served.
  - `innings` and `games` are 0 for **all** rows: `ingest_services.py` maps `n_games`/`innings`, columns the Savant OAA leaderboard does not provide. No playing-time field exists in the DB.
  - The leaderboard DOES provide `actual/adj_estimated/diff_success_rate` (per-opportunity OAA rate — playing-time-standardized) which the ingest silently dropped. **FIXED 2026-09-04**: Alembic `006` added the three columns; ingest parses the integer-percent strings; backfilled 2016–2025 (2,489 rows populated, spot-checked against the raw leaderboard; served via `/players/{id}/fielding` and shown as "OAA rate" in the profile UI). `innings`/`games` remain 0 — no upstream source in this leaderboard. Related sources noted for the reach re-derivation: `statcast_outfielder_jump` (reaction/burst/route distances, OF-only) and `statcast_outfield_catch_prob` (per-star opportunity counts → OF attempts).
  - Validation status of the reach model built on these fields: OF reach ranks realized OAA (+0.33); IF reach is noise (EXPERIMENTS.md 2026-09-04).

## `pitcher_profile`

- **Grain**: one row per (pitcher, season). Built nightly from `pitch_appearance` like spray. [VERIFIED]
- **Engine use**: only `groundball_pct` is consumed, via `pitcher_trajectory_weights` (clamped 0.6–1.5), to tilt ground-vs-air coverage; neutral when null. `xfip`/`siera` reserved NULL. [VERIFIED]

## `game_weather`

- **Grain**: per-game (`game_id`), Open-Meteo. Wind decomposed into `wind_x_component`/`wind_y_component`. Users may override inline via `WeatherInput`. Wind direction is meteorological "from" degrees (180 = blowing out to CF). [VERIFIED — CLAUDE.md]
- **Domain-reported distrust (user, 2026-09-02)**: of all data/model components, the user trusts the weather carry/drift factors least — they are hand-set and have never been outcome-checked. [ASSUMED as a severity signal; verification path: outcome-check `engine.carry_factor` against realized fly-ball carry by temperature/wind/altitude — tracked as the P3 weather-validation item in ROADMAP.md]

## `defensive_alignment` (history)

- **Grain**: one row per recommendation/scored alignment. Captures scenario, positions JSON, model outputs (`predicted_oaa_delta/hit_pct/out_pct`, `confidence`), `model_version`, `factors_used`. Written best-effort. [VERIFIED]
- **Potential asset**: this is the only place model outputs are logged with full scenario — a natural substrate for a future outcome-linked evaluation if joined to realized results. [INFERRED]

## `player_injury`

- **Grain**: active/historical injuries with multiplicative degradation factors applied at read time (`AdjustedProfile`); stored profiles never mutated. [VERIFIED]
