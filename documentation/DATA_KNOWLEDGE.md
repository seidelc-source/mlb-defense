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
  - `fielding_zone` derived via `_fielding_zone_from_hc` = nearest of 8 hand-placed `ZONE_CENTERS` after a **"rough normalization"** (`nx=(hc_x-25)/200`, `ny=1-(hc_y)/200`). Calibration of the constants against real field geometry is **unverified** — a systematic coordinate offset would misassign zones. [VERIFIED — code comment literally says "rough"]
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

## `pitcher_profile`

- **Grain**: one row per (pitcher, season). Built nightly from `pitch_appearance` like spray. [VERIFIED]
- **Engine use**: only `groundball_pct` is consumed, via `pitcher_trajectory_weights` (clamped 0.6–1.5), to tilt ground-vs-air coverage; neutral when null. `xfip`/`siera` reserved NULL. [VERIFIED]

## `game_weather`

- **Grain**: per-game (`game_id`), Open-Meteo. Wind decomposed into `wind_x_component`/`wind_y_component`. Users may override inline via `WeatherInput`. Wind direction is meteorological "from" degrees (180 = blowing out to CF). [VERIFIED — CLAUDE.md]

## `defensive_alignment` (history)

- **Grain**: one row per recommendation/scored alignment. Captures scenario, positions JSON, model outputs (`predicted_oaa_delta/hit_pct/out_pct`, `confidence`), `model_version`, `factors_used`. Written best-effort. [VERIFIED]
- **Potential asset**: this is the only place model outputs are logged with full scenario — a natural substrate for a future outcome-linked evaluation if joined to realized results. [INFERRED]

## `player_injury`

- **Grain**: active/historical injuries with multiplicative degradation factors applied at read time (`AdjustedProfile`); stored profiles never mutated. [VERIFIED]
