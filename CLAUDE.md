# MLB Defensive Positioning App

## Project overview
Full-stack baseball defensive analytics tool — FastAPI backend + React frontend.
See `backend/app/app_structure.md` and `backend/app/data_models.md` for full design context.

## Stack
- **Backend**: Python 3.11, FastAPI, SQLAlchemy async, Postgres, Redis, pybaseball
- **Frontend**: React 18, TypeScript, Vite, Zustand, TanStack Query, D3, Tailwind

## Running locally (quickstart)
```bash
# One command (Homebrew-based Postgres/Redis, no Docker):
python start.py

# Or manually — see STARTUP.md for the full guide.
```

## Data bootstrap (one-time)
```bash
cd backend
python -m scripts.seed                                            # 30 teams + stadiums
python -m scripts.ingest_all --season 2024 --start 2024-03-28 --end 2024-09-29
# (large date ranges are fine — pitches are deduped and re-runs are idempotent;
#  use --statcast-only to backfill pitch data without redoing rosters/fielding)
python -m scripts.smoke                                           # end-to-end check
```

## Backend layout
- `app/main.py`          — FastAPI app factory, lifespan, router mounts
- `app/config.py`        — Settings (reads .env)
- `app/core/`            — database, redis, logging, exceptions
- `app/models/`          — SQLAlchemy ORM models
- `app/schemas/schemas.py` — All Pydantic request/response models
- `app/repositories/repositories.py` — All data access
- `app/services/`        — Business logic (alignment engine, injury, weather, ingest)
- `app/routers/`         — HTTP layer (players.py + routers.py)
- `app/workers/scheduler.py` — APScheduler background jobs

## Frontend layout
- `src/types/index.ts`   — All TypeScript types (mirror backend schemas)
- `src/api/`             — Axios API clients
- `src/stores/`          — Zustand global state
- `src/hooks/`           — TanStack Query hooks
- `src/lib/fieldCoords.ts` — Coordinate math (Statcast ↔ normalized ↔ SVG)
- `src/components/`      — field/, panels/, charts/, ui/
- `src/pages/`           — FieldView, SprayAnalysis, PlayerProfile, IngestDashboard

## Testing
- Backend: `cd backend && python -m pytest tests/` (unit + integration, no DB needed)
- Frontend: `cd frontend && npm test` (vitest) and `npm run typecheck`
- End-to-end: `cd backend && python -m scripts.smoke` (needs running backend + data)
- CI: `.github/workflows/ci.yml` runs all of the above on push/PR

## Key conventions
- All coordinates use normalized 0–1 grid (see `fieldCoords.ts`)
- Injury degradation is multiplicative — never mutates stored profiles
- Cache keys: `alignment:{sha1_of_request}`, `spray:{player_id}:{season}:{scenario_hash}`
- Shift legality (MLB 2023+): 2 infielders each side of 2B, all on the dirt —
  enforced in `services/alignment/engine.py` (`is_legal_position`)
- Transport grids are downsampled to 50×50; frontend scales heatmaps by max cell
- Out-probability calibration: served numbers go through the versioned
  per-trajectory isotonic artifact (`services/alignment/artifacts/
  out_calibrator_v1.json`, loaded by `services/alignment/calibration.py`; refit
  with `scripts/fit_calibrator.py`, which enforces a reliability gate). The
  expectation runs over the batter's EMPIRICAL landing density
  (`services/alignment/landing.py` + `league_landing_v1.json`; rebuild with
  `scripts/build_league_landing.py`). Claim discipline: `predicted_oaa_delta`
  is direction-validated; absolute `predicted_hit_pct`/`out_pct` are
  population-level calibrated only (never rank batters by them — TRUST_REPORT
  2026-09-03). Raw engine `coverage` is internal-only. Responses carry
  `calibrator_version` + `landing_source`
- Spray "Total" (season=0) blends all seasons with per-year recency decay
  (`spray_recency_decay`, default 0.72 ≈ 2-yr half-life): rate fields are
  recency-weighted, but hit/out/total counts stay honest raw sums. Pass
  `recency_weighted=false` for a flat sample-weighted average. Single-season
  requests are unaffected. Season dropdowns are data-driven (`/spray/{id}/seasons`,
  `/players/{id}/fielding/seasons`) — never hardcode the season list
- Weather: the engine drifts fly balls with crosswind and deepens/shortens them
  via `engine.carry_factor` (temperature, stadium altitude, humidity, wind out/in);
  grounders are largely unaffected. Users set conditions manually via the
  `weather` field on the alignment request (`WeatherInput` → transient
  `GameWeather`); `POST /weather/preview` previews carry/drift. Wind direction is
  meteorological "from" degrees (deg 180 = blowing out to CF)
- Pitcher tendency: `PitcherProfile` is aggregated from pitches by
  `services/ingest/pitcher_aggregate.py` (nightly + historical backfill). The
  engine's `pitcher_trajectory_weights` tilts ground-vs-air coverage by the
  pitcher's `groundball_pct` (neutral when absent) — this is the `"pitcher_type"`
  factor. xFIP/SIERA are reserved (NULL, would need a FanGraphs pull)
- Park geometry: curated 5-point dims in `services/park_data.py`, wall polyline
  via `GET /stadiums/{id}/layout`, rendered by `components/field/ParkField.tsx`
  (1.0 norm = 400 ft; walls may slightly exceed 1.0 — SVG viewBox is padded)
- Static demo (GitHub Pages): `VITE_DEMO_MODE=true` builds run entirely from
  prebaked fixtures in `frontend/public/demo-data/` via an axios adapter
  (`src/demo/adapter.ts`) — curated matchups + weather presets only; drag
  re-scoring, ingest, and injury editing disabled. Regenerate fixtures with a
  running backend: `cd backend && python -m scripts.build_demo_fixtures`.
  Deployed by `.github/workflows/pages.yml`; demo routing uses HashRouter
- UI theme: light "paper & field" palette via CSS vars in `src/index.css`
  (`--paper`, `--ink`, `--clay`, `--gold`, `--field`); panels use `.panel`,
  `.panel-kicker`, `.stat-pill`, `.btn-chip` component classes

# Principal Data Scientist Methodology

This project uses the centralized Principal DS methodology (skill: `principal-ds`, installed at `~/.claude/skills/principal-ds/`). For substantial data/ML/analytics work, that skill's operating contract applies: data and target correctness before model optimization, point-in-time discipline, baseline-first modeling, evidence labels (VERIFIED / INFERRED / ASSUMED / HYPOTHESIS / UNKNOWN).

Project-specific knowledge lives in `documentation/` — read the relevant file before analytical work and update it when meaningful knowledge changes:

- `documentation/PROJECT_OPERATING_CONTRACT.md` — objective, decision, analytical unit, target, horizon, metrics, validation
- `documentation/DATA_KNOWLEDGE.md` — what is known about the data (grain, quirks, defects)
- `documentation/DATA_SOURCES.md` — source inventory and assessments
- `documentation/DATA_MAP.md` — connection map: how datasets join (keys, grains, temporal rules) and what each joined grain can answer
- `documentation/MODELING.md` — baselines, models, validation results
- `documentation/EXPERIMENTS.md` — experiment log, including negative results
- `documentation/ARCHITECTURE.md` — pipeline and system structure
- `documentation/DATA_GAP_ANALYSIS.md` — missing information and candidate sources
- `documentation/TRUST_REPORT.md` — current trust status and blocking issues
- `documentation/ROADMAP.md` — living P0–P3 plan with kill criteria, decision points, and change log
- `documentation/IDEAS.md` — the domain expert's ideas ledger: hunches in plain language, their data-terms translation, and status
- `documentation/PROMOTION_PROPOSALS.md` — candidate lessons proposed for the central methodology (never auto-applied)

Rules:

- Project facts stay in this repository; never edit the central skill from project work.
- Do not optimize models before checking target, data, point-in-time correctness, leakage, baselines, and validation.
- Preserve validated historical findings unless new evidence contradicts them; when evidence conflicts, investigate and label the status.
- A meaningful analytical change is complete only when implementation, validation, reproducibility, and the relevant documentation are updated — including refreshing the changed file's TL;DR line.
- Lead substantive reports with a plain-language Bottom line per the communication preference below; technical detail follows.

## Project summary

- **Objective**: Recommend legal defensive fielder positioning (7 fielders) for a given batter × pitcher × stadium × weather × game-state scenario, to maximize expected outs vs. the standard alignment. The intended claim is **out-conversion prediction**, not mere physical plausibility — numbers shown must be outcome-validated and calibrated. [VERIFIED — user, 2026-09-02]
- **Decision supported**: The project is a **portfolio/demo piece**: the win is a credible, honest demo whose claims hold up to scrutiny. In-app framing: a coach/analyst chooses where to position fielders pre-pitch from top-N candidate alignments with a predicted out-conversion delta. [VERIFIED (purpose) — user, 2026-09-02; INFERRED (in-app framing)]
- **Analytical unit**: One prediction = one scenario → an alignment (`{position: (x,y)}`). Underlying data grain: `pitch_appearance` = 1 row/pitch; `batter_spray_profile` = 1 row/(player, season, scenario, fielding_zone). [VERIFIED]
- **Target**: None trained. The engine is a **deterministic heuristic** whose coverage surface at the standard alignment has been outcome-evaluated and recalibrated (per-trajectory isotonic; per-ball map VERIFIED, served via the versioned artifact). Serving aggregates it under the batter's empirical landing density (2026-09-03): absolute `predicted_hit_pct`/`out_pct` are population-level calibrated (bias +0.005) but carry no validated batter-level signal — claims capped permanently per the pre-registered kill criterion; `oaa_delta` direction-validated. [VERIFIED — see `documentation/MODELING.md`, `documentation/EXPERIMENTS.md`]
- **Prediction horizon / prediction-time constraints**: Live pre-pitch decision using the latest fielding profiles + recency-weighted all-season spray blend. Any retrospective backtest must control point-in-time (latest profiles and season-aggregate spray include future/outcome info). [INFERRED]
- **Primary metric & success criterion**: Descriptive — log loss / Brier / AUC vs zone-lookup baselines (LOSO by season); calibrated surface beats both baselines with CI separation. Prescriptive — realized out-rate lift vs standard alignment (within-batter policy-value estimator). [VERIFIED — see `documentation/EXPERIMENTS.md`]
- **Communication preference**: plain-first — lead with a plain-language bottom line; technical detail follows. [user, 2026-09-02]
- **Current trust status**: CONDITIONALLY TRUSTED for the calibrated P(out | standard-alignment) surface and handedness-corrected positioning direction; the pull-based shift/no-shift *decision* heuristic is NOT validated as adding value over shifting broadly; fine x,y placement UNKNOWN (data gap). See `documentation/TRUST_REPORT.md`.
