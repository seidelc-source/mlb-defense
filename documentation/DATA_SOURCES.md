# Data Sources

> Project-specific inventory of current and candidate data sources. One record per source. Keep rejected sources with the rejection reason — that reasoning is reusable.

## Statcast (via pybaseball) — CURRENT

- **Provider / owner**: MLB / Baseball Savant, accessed through the `pybaseball` library.
- **Access path**: Python library scraping/API; stability subject to upstream Savant changes and rate limits. [INFERRED]
- **Grain**: one row per pitch → `pitch_appearance`.
- **Coverage & historical depth**: 2016–2025 loaded (`ingest_historical` SEASONS map). [VERIFIED — CLAUDE.md]
- **Update / revision behavior**: nightly ingest of prior day; upstream revisions to tracking data not explicitly reconciled. [ASSUMED]
- **Point-in-time availability**: batted-ball location/result available post-play; suitable for live decisions the next game. [INFERRED]
- **Quality assessment**: rich batted-ball physics (`hc_x/hc_y`, `launch_angle`, `launch_speed`); but the project only uses coarse 8-zone binning of location. [VERIFIED]
- **Licensing / cost**: public Savant data; respect rate limits. [ASSUMED]
- **Integration effort**: done.
- **Expected analytical value**: primary substrate for spray + pitcher tendencies.
- **Decision & rationale**: CURRENT — core dependency.

## MLB Stats API / Statcast fielding leaderboards — CURRENT

- **Provider / owner**: MLB.
- **Access path**: API / leaderboard sync (`fielding_weekly`).
- **Grain**: one row per (player, season, position) → `fielding_profile`; includes OAA, sprint speed, reaction, route efficiency, arm.
- **Point-in-time availability**: leaderboards update in-season; engine uses **latest** → future-leaning for historical scenarios. [INFERRED]
- **Quality assessment**: authoritative fielder athleticism metrics; **OAA here is an untapped ground-truth candidate** (see DATA_GAP_ANALYSIS). [INFERRED]
- **Decision & rationale**: CURRENT.

## Open-Meteo — CURRENT

- **Provider / owner**: Open-Meteo.
- **Access path**: HTTP API (`weather_hourly`), plus manual `WeatherInput` override.
- **Grain**: per-game conditions → `game_weather`; wind decomposed x/y.
- **Point-in-time availability**: forecast vs. actual not distinguished in storage; for live use forecast is appropriate. [INFERRED]
- **Decision & rationale**: CURRENT.

## Curated park geometry — CURRENT

- **Provider / owner**: in-repo (`services/park_data.py`, `enrich_stadiums.py`).
- **Grain**: 5-point outfield dimensions + wall polyline per stadium.
- **Quality assessment**: curated constants; fence-legality depends on their accuracy. [INFERRED]
- **Decision & rationale**: CURRENT.

## Realized batted-ball outcome linked to actual alignment — CANDIDATE (see gap analysis)

- **Provider / owner**: derivable from Statcast (some seasons include fielder alignment / infield-shift flags and hit outcome).
- **Expected analytical value**: the missing ground truth needed to validate `predicted_oaa_delta` / `predicted_hit_pct` and to build an external baseline. [INFERRED]
- **Decision & rationale**: CANDIDATE — highest-value acquisition; see `documentation/DATA_GAP_ANALYSIS.md`.

## Per-play fielder start coordinates — CANDIDATE (unlocks P1 Tier-2: fine placement)

- **Provider / owner**: MLB Statcast player-tracking (Hawk-Eye). Exact (x, y) of each fielder at pitch release/contact.
- **Access path**: not in the ingested `pybaseball.statcast()` feed; available for recent seasons via Statcast player-tracking / fielder-alignment endpoints (e.g. Baseball Savant tracking exports, `statsapi` tracking, or a licensed feed). Access stability and historical depth **UNKNOWN — needs investigation**. [ASSUMED]
- **Grain**: one row per play per fielder (position → x, y).
- **Coverage & historical depth**: tracking-era only; likely partial/absent before ~2020 and possibly gated. [UNKNOWN]
- **Point-in-time availability**: positions are set at pitch release → genuinely pre-outcome; clean for both live and retrospective use. [INFERRED]
- **Quality assessment**: would be the authoritative input for validating the engine's **fine-grained x,y placement** (its local-search selling point), which is currently **UNKNOWN** — untestable without it. Would also replace template positions in P1's out-model scoring, removing threat (4) there.
- **Licensing / cost / integration effort**: UNKNOWN — the investigation is the first step.
- **Expected analytical value**: **high** — the only path to validating fine placement and to a non-categorical prescriptive evaluation. Until acquired, fine placement stays UNKNOWN by design.
- **Decision & rationale**: CANDIDATE. Gated behind P1's categorical result — pursue if the categorical shift recommendation validates (worth investing in fine placement) or if fine placement is the specific bottleneck. See DATA_GAP_ANALYSIS.

## FanGraphs (xFIP / SIERA) — REJECTED (for now)

- **Decision & rationale**: REJECTED — `xfip`/`siera` columns reserved NULL; would require a separate FanGraphs pull and are **not consumed by the engine**. Not worth the integration cost until an evaluation shows pitcher modeling is the bottleneck. [VERIFIED — data_models.md]
