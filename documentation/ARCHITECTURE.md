# Architecture

> Project-specific system knowledge: how data flows from sources to decisions. Label claims: VERIFIED / INFERRED / ASSUMED / HYPOTHESIS / UNKNOWN.
> Full engineering detail lives in `backend/app/app_structure.md` and `backend/app/data_models.md`; this file focuses on the analytical/data-flow view.

## Pipeline overview

```
Statcast (pybaseball) ──► pitch_appearance          (1 row/pitch; derived fielding_zone, result, trajectory)
MLB Stats API / leaderboards ──► fielding_profile, pitcher_profile, player, team, stadium
Open-Meteo ──► game_weather

  pitch_appearance ──(nightly SprayAggregateService)──► batter_spray_profile   (per zone/scenario)
  pitch_appearance ──(nightly PitcherAggregateService)─► pitcher_profile

  AlignmentService.recommend(scenario)
     ├─ spray_blend.merge_zone_rows (recency-weighted all-season blend)
     ├─ latest fielding_profile per fielder  ─► InjuryService (AdjustedProfile, multiplicative)
     ├─ latest pitcher_profile (if "pitcher_type" factor)
     ├─ weather (manual WeatherInput or fetched)
     └─ engine.compute_alignment ──► top-N AlignmentCandidate ──► AlignmentResponse
                                                              └─► defensive_alignment (history, best-effort)
```

- **Point-in-time enforcement**: none explicit. Live use is present-time-correct by construction. There is **no** as-of/temporal filter that would make a *retrospective* run point-in-time honest (latest profiles + season-aggregate spray both leak future info). [INFERRED]

## Components

| Component | Owns | Entry point |
|---|---|---|
| `services/ingest/ingest_services.py` | Statcast/fielding/player ingest, derived-field construction (`_fielding_zone_from_hc`, `_general_result`, `_ball_trajectory`) | `scripts/ingest_all`, `ingest_historical` |
| `services/ingest/spray_aggregate.py` | Rebuild `batter_spray_profile` per season | nightly `spray_aggregate` job |
| `services/ingest/pitcher_aggregate.py` | Rebuild `pitcher_profile` per season | nightly `pitcher_aggregate` job |
| `services/spray_blend.py` | Recency-weighted cross-season zone merge | `merge_zone_rows` |
| `services/alignment/engine.py` | Pure heuristic: grids, reach, scoring, legality, local search | `compute_alignment`, `score_custom_positions` |
| `services/alignment/service.py` | Orchestration, caching, persistence, response shaping | `AlignmentService.recommend`, `score_custom` |
| `services/injury_service.py` | Multiplicative degradation at read time | `AdjustedProfile` |
| `services/weather_service.py`, `weather_fetch.py`, `park_data.py`, `park_layout.py` | Weather decomposition, park geometry | `carry_factor`, `wall_distance_at` |
| `workers/scheduler.py` | APScheduler batch jobs (see app_structure.md table) | lifespan |

## Environments & reproducibility

- Local: `python start.py` (Homebrew Postgres/Redis) or `STARTUP.md`. [VERIFIED]
- Bootstrap: `scripts/seed` → `scripts/ingest_all`/`ingest_historical` → `scripts/smoke`. Idempotent re-runs. [VERIFIED]
- Engine is deterministic (no seeds needed). Tunables centralized in `config.py`. [VERIFIED]
- Tests: `pytest tests/` (no DB needed for unit); `scripts/smoke` end-to-end (needs running backend + data). [VERIFIED]

## Architectural risks

- **Correctness depends on convention, not enforcement**:
  - Coordinate calibration (`hc_x/hc_y` → normalized grid; 1 unit = 400 ft) is by hand-set constants, not validated against field landmarks — a silent offset misassigns zones. [VERIFIED]
  - Point-in-time honesty for any future backtest is not enforced by the data layer (`get_latest_profile`, season-aggregate spray). [INFERRED]
  - Model output labels (`predicted_hit_pct`, `predicted_oaa_delta`) read as real probabilities/OAA but are internal coverage quantities — risk of over-interpretation by consumers. [INFERRED]
- **Single async session**: queries must be sequential (documented) — not an analytical risk but a correctness constraint. [VERIFIED]
