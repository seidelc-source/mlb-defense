# Data Models

The persistent data model (SQLAlchemy async, Postgres). Models live in
`app/models/`; this doc is the design-level map. For how they're consumed, see
[app_structure.md](app_structure.md).

All tables inherit `UUIDMixin` (UUID `id` PK) and `TimestampMixin`
(`created_at` / `updated_at`) from `models/base.py`.

## Entity overview

```
team ──< player ──< fielding_profile
  │         ├──< pitcher_profile        (scaffolding — see note)
  │         ├──< batter_spray_profile   (nightly aggregate)
  │         └──< player_injury
  └── home_stadium ── stadium
pitch_appearance   (raw fact table: pitcher_id, batter_id, stadium_id FKs)
defensive_alignment (history: batter/pitcher/stadium/weather FKs)
game_weather
```

## Reference / dimension tables

### `team` (`team.py`)
30 MLB teams. Key cols: `mlb_team_id`, `name`, `abbreviation`, `league`,
`division`, `home_stadium_id` → `stadium`. Relationship: `players`.

### `stadium` (`stadium.py`)
Parks + geometry used by the engine and `ParkField` rendering. Location
(`latitude`/`longitude`/`altitude_ft`), `roof_type`, `surface`, curated
dimensions (`left_line_ft`, `left_center_ft`, `center_ft`, `right_center_ft`,
`right_line_ft`), wall heights, and park factors (`park_factor_runs`,
`park_factor_hr`). Seeded by `scripts/seed.py` + `scripts/enrich_stadiums.py`.

### `player` (`player.py`)
People. Cross-source IDs (`mlbam_id`, `fangraphs_id`, `bbref_id`, `lahman_id`),
`full_name`, `position`, `throws`, `bats`, `active`, `team_id`. Relationships:
`team`, `fielding_profiles`, `pitcher_profiles`, `injuries`. `throws` is the
source of pitcher handedness used in spray scenarios.

## Fact table

### `pitch_appearance` (`pitch_appearance.py`)
One row per pitch — the raw Statcast feed and the source everything aggregates
from. `mlb_play_id` is the unique de-dupe key. Holds pitch tracking
(`pitch_type`, `release_speed_mph`, `spin_rate`, `pfx_x/z`, `plate_x/z`, `zone`),
count/state (`balls`, `strikes`, `outs_when_up`, `inning`, `inning_half`),
batted-ball physics (`launch_angle`, `launch_speed`, `hit_distance_sc`, `hc_x`,
`hc_y`), and **derived** classification used downstream:
- `fielding_zone` (1–8) — the zone the ball was hit into.
- `general_result` (`hit` / `out`), `specific_result` (`single`…`hr`/`error`),
  `ball_trajectory` (`groundball` / `flyball` / `linedrive` / `popup`).

Largest table by far (~700k–750k rows per full season; 2016–2025 loaded).

## Derived / aggregate tables

### `batter_spray_profile` (`remaining_models.py`)
Pre-aggregated zone distributions, rebuilt nightly from `pitch_appearance` by
`SprayAggregateService`. **One row per (player, season, scenario, fielding_zone).**

- **Scenario keys** — `pitch_type`, `pitcher_hand`, `pitch_speed_min/max`,
  `count_state`. **NULL means "all"**: the all-pitches/all-hands/all-speeds
  aggregate has every scenario field NULL. Per-scenario rows are only written
  above a sample floor.
- **Counts** — `hit_count`, `out_count`, `total_batted_balls`, `sample_n`.
- **Rates** — `hit_pct`, `out_pct`; trajectory (`groundball_pct`…`popup_pct`);
  specific (`single_pct`…`error_pct`).
- Read via `SprayRepository.get_zones`; `season=None` spans all seasons and is
  collapsed by `spray_blend.merge_zone_rows` (recency-weighted "Total").

### `fielding_profile` (`fielding_profile.py`)
One row per (player, season, position). Statcast fielding metrics:
`outs_above_average` (+ directional `oaa_back/in/left/right`),
`fielding_run_value`, `sprint_speed_ft_s`, `range_pct_vs_avg`, `reaction_time_s`,
`route_efficiency_pct`, `arm_strength_mph`, `arm_accuracy_pct` (each with a 1–5
`*_level` band), plus catcher-specific `framing_runs` / `blocking_runs` /
`catcher_throwing_runs`. Synced weekly for the current season. The engine uses
the **latest** profile per fielder (`get_latest_profile`), adjusted for injuries.

### `pitcher_profile` (`pitcher_profile.py`)
One row per (pitcher, season): `pitcher_type` (groundball / flyball / strikeout /
neutral), `role` (SP/RP heuristic), batted-ball rates (`groundball_pct`…
`popup_pct`), `strikeout_pct` / `walk_pct`, velocity (`avg_velocity_mph`,
`avg_fastball_mph`, `max_fastball_mph`), `spin_rate_avg`, and `pitch_mix` (JSON
`{type: share}`). Built by `PitcherAggregateService` from `pitch_appearance`
(nightly + historical backfill), exactly like spray aggregation. `xfip`/`siera`
are reserved (NULL) — they'd require a FanGraphs pull and aren't used by the
engine. The alignment engine reads `groundball_pct` via
`engine.pitcher_trajectory_weights` to tilt ground-vs-air fielder positioning,
which is what makes the `"pitcher_type"` factor in `AlignmentRequest` active.

## Operational tables

### `game_weather` (`remaining_models.py`)
Per-game conditions (Open-Meteo), keyed by `game_id`. Temperature, humidity,
wind (`wind_speed_mph`, `wind_direction_deg`, label, 1–5 level), pressure, and
**decomposed `wind_x_component` / `wind_y_component`** for the engine. Optional
FK to `stadium`.

### `defensive_alignment` (`remaining_models.py`)
History of recommendations and scored alignments (`alignment_type`). Captures
the full scenario (batter/pitcher/stadium/weather FKs, game state — inning,
outs, `on_1b/2b/3b`, `score_diff`), the result (`shift_type`,
`fielder_positions` JSON `{pos: {player_id, x, y, depth_ft, angle_deg}}`), model
outputs (`predicted_oaa_delta`, `predicted_hit_pct`, `predicted_out_pct`,
`confidence`), and metadata (`factors_used`, `optimize_for`, `model_version`).
Written best-effort — a persistence failure never fails the request.

### `player_injury` (`remaining_models.py`)
Active/historical injuries. `body_part`, `severity` (mild/moderate/severe),
`active`, dates, free-text `notes`, and **multiplicative degradation factors**
(`speed_factor`, `arm_strength_factor`, `arm_accuracy_factor`, `reaction_factor`,
`range_factor`; 1.0 = full ability). `InjuryService` applies these at read time
against a copy of the fielding profile — stored metrics are never mutated.

## Conventions
- Fielding zones are integers 1–8 (per the source paper's Table 2).
- Field coordinates are normalized 0–1 (1.0 ≈ 400 ft); see frontend
  `lib/fieldCoords.ts`.
- Cross-source player IDs let ingest reconcile pybaseball / MLB Stats API.
- Schema changes go through Alembic (`alembic_version` tracks the head).
