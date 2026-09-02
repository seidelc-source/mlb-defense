# Backend Architecture

Design context for the FastAPI backend. For the data tables themselves, see
[data_models.md](data_models.md). For day-to-day commands, see the root
`CLAUDE.md` and `STARTUP.md`.

## Layering

The backend is a conventional layered FastAPI app. Each layer only talks to the
one below it:

```
routers/        HTTP layer — request/response, validation, status codes
  └─ services/  Business logic — alignment engine, injury, weather, ingest
       └─ repositories/  Data access — all SQLAlchemy queries live here
            └─ models/   ORM table definitions
```

- **`main.py`** — app factory, lifespan (starts/stops the scheduler), router mounts.
- **`config.py`** — `Settings` (pydantic-settings, reads `.env`). All tunables
  live here, including `spray_recency_decay` and the `alignment_*` knobs.
- **`core/`** — cross-cutting infra: `database.py` (async engine + `get_session`
  dependency), `redis.py` (`cache_get`/`cache_set`), `logging.py`, `exceptions.py`
  (`NotFoundError`, `InsufficientDataError`, etc., mapped to HTTP codes).
- **`schemas/schemas.py`** — every Pydantic request/response model in one file.
- **`repositories/repositories.py`** — every repository in one file. Repos are
  thin: one `AsyncSession`, query methods returning ORM objects. **No raw SQL or
  query construction leaks above this layer.**
- **`services/`** — orchestration and domain logic (see below).
- **`routers/`** — `players.py` (player/fielding/injury endpoints) and
  `routers.py` (spray, alignments, range, weather, stadiums, ingest). Routers
  depend on `SessionDep` and delegate to repos/services.
- **`workers/scheduler.py`** — APScheduler jobs, started in lifespan.

> One `AsyncSession` cannot run queries concurrently — fetch sequentially within
> a request, not via `asyncio.gather`. (See the note in `alignment/service.py`.)

## Request flow: alignment recommendation

`POST /api/v1/alignments/recommend` is the core path and exercises most layers:

1. **Router** (`routers.py`) validates the `AlignmentRequest` and calls
   `AlignmentService.recommend()`.
2. **Cache check** — `alignment:{sha1(request)}` in Redis; hit returns immediately.
3. **Data fetch** (sequential, one session):
   - Spray zones via `_spray_zones()` → recency-weighted blend across **all**
     seasons (`spray_blend.merge_zone_rows`, decay = `spray_recency_decay`).
   - Latest fielding profile per rostered fielder.
   - Latest pitcher profile (when `"pitcher_type"` is in `include_factors`).
   - Optional game weather.
4. **Injury adjustment** — `InjuryService` applies multiplicative degradation
   factors to each fielder profile (never mutates stored rows). In-game
   `injury_override` on a roster entry takes precedence.
5. **Engine** — `alignment/engine.compute_alignment()` builds hit-probability
   grids (ground + air) from the spray zones, tilts the ground-vs-air balance by
   the pitcher's groundball tendency (`pitcher_trajectory_weights`), scores
   candidate alignments under shift-legality rules, and returns the top N.
6. **Response + persist + cache** — build `AlignmentResponse`, write a
   `DefensiveAlignment` history row, cache for `cache_ttl_alignment`.

`score_custom()` is the same minus optimization: it scores a user-arranged
alignment. It also routes spray through `_spray_zones()`, so passing `season=0`
scores against the recency-weighted blend.

## Key subsystems

### Alignment engine (`services/alignment/`)
- `engine.py` — pure functions: `build_hit_probability_grid`, `compute_alignment`,
  `score_custom_positions`, `compute_reach`, `is_legal_position`. No DB access.
  Coordinates are the normalized 0–1 grid; `GRID` = 100×100.
- `service.py` — orchestration (the flow above), persistence, caching, response
  shaping.
- **Shift legality (MLB 2023+):** 2 infielders on each side of 2B, all on the
  dirt — enforced by `is_legal_position`. Pre-2023 spray data is still ingested
  for tendencies; the engine applies current rules regardless.

### Spray blending (`services/spray_blend.py`)
Shared by the spray-chart endpoint and the alignment engine so both agree.
`merge_zone_rows(rows, recency_decay)` collapses per-season zone rows into one
aggregate: **counts stay honest raw sums**; rate fields are weighted averages
scaled by `recency_decay ** (latest_season - season)`. `decay = 1.0` = plain
sample-weighted average.

### Ingest (`services/ingest/`)
- `ingest_services.py` — `PlayerIngestService`, `StatcastIngestService`,
  `FieldingIngestService` (pull via pybaseball / MLB Stats API).
- `statcast.py`, `fielding.py` — thin module entry points used by the scheduler.
- `spray_aggregate.py` — `SprayAggregateService` rebuilds `BatterSprayProfile`
  from `PitchAppearance` (nightly). Writes per-zone rows for the "all" aggregate
  plus per pitch-type / pitcher-hand / speed-band scenarios above a sample floor.
- `pitcher_aggregate.py` — `PitcherAggregateService` rebuilds `PitcherProfile`
  from `PitchAppearance` (nightly): batted-ball tendencies, K/BB, velocity, spin,
  pitch mix. Feeds the engine's pitcher trajectory tilt.
- Bootstrap scripts: `scripts/ingest_all.py` (one season), `ingest_historical.py`
  (the 2016–2025 `SEASONS` map). Re-runs are idempotent (pitches deduped, spray
  rebuilt per season).

### Injury (`services/injury_service.py`)
`AdjustedProfile` applies active `PlayerInjury` factors multiplicatively to a
fielding profile at read time. Stored profiles are never mutated.

### Weather (`services/weather_service.py`, `weather_fetch.py`)
Fetches game-time weather (Open-Meteo) and decomposes wind into x/y components.
The engine's weather model (`engine.carry_factor` + `_weather_shift`) drifts fly
balls laterally with crosswind and deepens/shortens them with a **carry factor**
(temperature, stadium altitude, humidity, wind blowing out/in); grounders are
largely unaffected. Users can override conditions inline: an `AlignmentRequest`
may carry a `WeatherInput` (built into a transient `GameWeather` via
`build_manual_weather`), and `POST /weather/preview` returns the carry factor +
drift for live UI feedback. `park_data.py` / `park_layout.py` hold curated park
geometry.

## Background jobs (`workers/scheduler.py`)
APScheduler, UTC, gated by `worker_enabled`:

| Job | Schedule | Action |
|-----|----------|--------|
| `statcast_nightly` | 02:00 daily | ingest **yesterday's** pitches |
| `spray_aggregate` | 03:30 daily | rebuild current-season spray profiles |
| `pitcher_aggregate` | 03:45 daily | rebuild current-season pitcher profiles |
| `fielding_weekly` | Sun 04:00 | sync OAA / FRV / sprint-speed leaderboards |
| `weather_hourly` | hourly | fetch weather for today's games |

Each job opens its own session and is structured to extract cleanly to a Celery
task if the app needs to scale out.

## Caching
Redis, keys documented in `CLAUDE.md`:
- `alignment:{sha1_of_request}` — TTL `cache_ttl_alignment` (1h)
- `spray:{player_id}:{season}:{scenario_hash}` — TTL `cache_ttl_spray` (24h)

## Conventions
- Normalized 0–1 field coordinates everywhere (see frontend `lib/fieldCoords.ts`).
- Transport grids downsampled 100×100 → 50×50 before serialization.
- Season lists are data-driven (`/spray/{id}/seasons`,
  `/players/{id}/fielding/seasons`) — never hardcode the season list.
