"""
Remaining routers: spray, alignments, range, weather, stadiums, ingest.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import InsufficientDataError, NotFoundError
from app.repositories.repositories import (
    SprayRepository,
    StadiumRepository,
    WeatherRepository,
)
from app.schemas.schemas import (
    AlignmentHistoryItem,
    AlignmentRequest,
    AlignmentResponse,
    AlignmentScoreRequest,
    AlignmentScoreResponse,
    GameWeatherResponse,
    IngestJobResponse,
    IngestJobStatus,
    PlayerSummary,
    SprayChartResponse,
    SprayZone,
    StadiumLayoutResponse,
    StadiumResponse,
    TeamRangeResponse,
    TeamSummary,
    WeatherEffectResponse,
    WeatherInput,
)
from app.services.alignment.service import AlignmentService
from app.services.spray_blend import merge_zone_rows
from app.services.weather_service import WeatherService
from app.config import get_settings

settings = get_settings()
SessionDep = Annotated[AsyncSession, Depends(get_session)]


# ── Spray ─────────────────────────────────────────────────────────────────────

spray_router = APIRouter(prefix="/spray", tags=["spray"])

@spray_router.get("/{batter_id}/seasons", response_model=list[int])
async def get_spray_seasons(batter_id: uuid.UUID, session: SessionDep) -> list[int]:
    """Seasons with spray data for this batter (drives the UI dropdown)."""
    return await SprayRepository(session).get_seasons(batter_id)


@spray_router.get("/{batter_id}", response_model=SprayChartResponse)
async def get_spray_chart(
    batter_id: uuid.UUID,
    session: SessionDep,
    season: int = Query(default=2024, ge=0, description="0 = total across all seasons"),
    pitch_type: str | None = Query(default=None),
    pitcher_hand: str | None = Query(default=None, pattern="^[LRS]$"),
    speed_min: float | None = Query(default=None),
    speed_max: float | None = Query(default=None),
    recency_weighted: bool = Query(
        default=True,
        description="season=0 only: weight recent seasons more heavily",
    ),
) -> SprayChartResponse:
    from app.repositories.repositories import PlayerRepository
    player = await PlayerRepository(session).get_or_raise(batter_id)
    spray_repo = SprayRepository(session)
    zones = await spray_repo.get_zones(
        batter_id,
        None if season == 0 else season,
        pitch_type, pitcher_hand, speed_min, speed_max,
    )
    apply_recency = season == 0 and recency_weighted
    if season == 0:
        decay = settings.spray_recency_decay if recency_weighted else 1.0
        zones = merge_zone_rows(zones, decay)

    if not zones:
        raise NotFoundError("BatterSprayProfile", batter_id)

    total_n = sum(z.sample_n for z in zones)
    if total_n < settings.alignment_min_spray_sample:
        raise InsufficientDataError(str(batter_id), total_n, settings.alignment_min_spray_sample)

    from app.services.alignment.engine import build_hit_probability_grid

    hit_grid = build_hit_probability_grid(zones)

    # Halve transport size: downsample 100×100 → 50×50 and round.
    # Values stay a probability mass (sum ≈ 1); frontend scales by max.
    import numpy as np
    g = hit_grid.shape[0]
    if g % 2 == 0:
        hit_grid = hit_grid.reshape(g // 2, 2, g // 2, 2).mean(axis=(1, 3)) * 4
    hit_grid = np.round(hit_grid, 6)

    spray_zones = [
        SprayZone(
            zone=z.fielding_zone,
            hit_pct=z.hit_pct,
            out_pct=z.out_pct,
            trajectory={
                "groundball": z.groundball_pct,
                "flyball": z.flyball_pct,
                "linedrive": z.linedrive_pct,
                "popup": z.popup_pct,
            },
            specific={
                "single": z.single_pct,
                "double": z.double_pct,
                "triple": z.triple_pct,
                "hr": z.hr_pct,
                "error": z.error_pct,
            },
            n=z.sample_n,
        )
        for z in zones
    ]

    return SprayChartResponse(
        batter=PlayerSummary.model_validate(player),
        season=season,
        filters_applied={
            "pitch_type": pitch_type,
            "pitcher_hand": pitcher_hand,
            "speed_min": speed_min,
            "speed_max": speed_max,
        },
        zones=spray_zones,
        logistic_grid=hit_grid.tolist(),
        sample_n=total_n,
        recency_weighted=apply_recency,
    )


# ── Alignments ────────────────────────────────────────────────────────────────

alignment_router = APIRouter(prefix="/alignments", tags=["alignments"])


@alignment_router.post("/recommend", response_model=AlignmentResponse)
async def recommend_alignment(
    req: AlignmentRequest,
    session: SessionDep,
) -> AlignmentResponse:
    svc = AlignmentService(session)
    return await svc.recommend(req)


@alignment_router.post("/score", response_model=AlignmentScoreResponse)
async def score_custom_alignment(
    req: AlignmentScoreRequest,
    session: SessionDep,
) -> AlignmentScoreResponse:
    svc = AlignmentService(session)
    return await svc.score_custom(req)


@alignment_router.get("/{alignment_id}", response_model=AlignmentResponse)
async def get_alignment(alignment_id: uuid.UUID, session: SessionDep):
    from app.repositories.repositories import AlignmentRepository
    repo = AlignmentRepository(session)
    alignment = await repo.get_or_raise(alignment_id)
    return alignment


@alignment_router.get("", response_model=list[AlignmentHistoryItem])
async def get_alignment_history(
    session: SessionDep,
    batter_id: uuid.UUID | None = Query(default=None),
    pitcher_id: uuid.UUID | None = Query(default=None),
    team_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    from app.repositories.repositories import AlignmentRepository
    repo = AlignmentRepository(session)
    items = await repo.get_history(
        batter_id=batter_id,
        pitcher_id=pitcher_id,
        team_id=team_id,
        limit=limit,
    )
    return [AlignmentHistoryItem.model_validate(i) for i in items]


# ── Range ─────────────────────────────────────────────────────────────────────

range_router = APIRouter(prefix="/range", tags=["range"])


@range_router.get("/{player_id}")
async def get_player_range(
    player_id: uuid.UUID,
    session: SessionDep,
    position: str | None = Query(default=None),
    season: int = Query(default=2024),
    injury_active: bool = Query(default=True),
):
    from app.repositories.repositories import FieldingRepository, PlayerRepository
    from app.services.alignment.engine import compute_reach, STANDARD_POSITIONS
    from app.services.injury_service import InjuryService
    from app.schemas.schemas import PlayerRangeResponse

    player = await PlayerRepository(session).get_or_raise(player_id)
    fielding_repo = FieldingRepository(session)
    profile = await fielding_repo.get_latest_profile(player_id, position)

    if profile is None:
        raise NotFoundError("FieldingProfile", player_id)

    if injury_active:
        svc = InjuryService(session)
        adjusted = await svc.apply_for_player(profile)
    else:
        from app.services.injury_service import AdjustedProfile
        adjusted = AdjustedProfile.from_profile(profile)

    pos = profile.position
    cx, cy = STANDARD_POSITIONS.get(pos, (0.5, 0.5))
    reach = compute_reach(
        player_id=player_id,
        position=pos,
        center_x=cx,
        center_y=cy,
        sprint_speed=adjusted.sprint_speed_ft_s,
        reaction_time=adjusted.reaction_time_s,
        route_efficiency=adjusted.route_efficiency_pct if hasattr(adjusted, "route_efficiency_pct") else None,
    )

    return PlayerRangeResponse(
        player_id=player_id,
        player_name=player.full_name,
        position=pos,
        center_x=cx,
        center_y=cy,
        # Reach radii are computed in normalized units (1.0 = 400 ft) —
        # convert to feet for the API
        radii={
            "zone_075s": round(reach.r_075s * 400, 1),
            "zone_125s": round(reach.r_125s * 400, 1),
            "zone_175s": round(reach.r_175s * 400, 1),
            "zone_225s": round(reach.r_225s * 400, 1),
            "zone_300s": round(reach.r_300s * 400, 1),
        },
        arm_throw_range={
            "max_distance_ft": (adjusted.arm_strength_mph or 80.0) * 2.5,
            "accuracy_pct": adjusted.arm_accuracy_pct or 75.0,
        },
        effective_zones=[1, 2, 3, 4, 5, 6, 7, 8],
        injury_adjusted=bool(adjusted.injuries_applied),
    )


# ── Weather ───────────────────────────────────────────────────────────────────

weather_router = APIRouter(prefix="/weather", tags=["weather"])


@weather_router.get("/game/{game_id}", response_model=GameWeatherResponse)
async def get_game_weather(game_id: str, session: SessionDep):
    repo = WeatherRepository(session)
    weather = await repo.get_by_game_id(game_id)
    if weather is None:
        raise NotFoundError("GameWeather", game_id)
    return GameWeatherResponse.model_validate(weather)


@weather_router.get("/current/{stadium_id}", response_model=GameWeatherResponse | None)
async def get_current_weather(stadium_id: uuid.UUID, session: SessionDep):
    svc = WeatherService(session)
    return await svc.fetch_current(stadium_id)


@weather_router.post("/preview", response_model=WeatherEffectResponse)
async def preview_weather(
    body: WeatherInput,
    session: SessionDep,
    stadium_id: uuid.UUID | None = Query(default=None),
):
    """Preview how given conditions bend batted balls (carry + drift) without
    running a full alignment — drives live feedback in the manual weather panel."""
    from app.services.alignment.engine import carry_factor
    from app.services.weather_service import build_manual_weather, describe_weather

    altitude = 0.0
    if stadium_id is not None:
        stadium = await StadiumRepository(session).get(stadium_id)
        if stadium is not None and stadium.altitude_ft is not None:
            altitude = float(stadium.altitude_ft)

    weather = build_manual_weather(stadium_id, body)
    cf = carry_factor(weather, altitude)
    return WeatherEffectResponse(
        wind_x_component=weather.wind_x_component,
        wind_y_component=weather.wind_y_component,
        wind_direction_label=weather.wind_direction_label,
        wind_speed_level=weather.wind_speed_level,
        carry_factor=round(cf, 4),
        carry_pct=round((cf - 1.0) * 100, 1),
        summary=describe_weather(cf, weather),
    )


# ── Teams ─────────────────────────────────────────────────────────────────────

team_router = APIRouter(prefix="/teams", tags=["teams"])


@team_router.get("", response_model=list[TeamSummary])
async def list_teams(session: SessionDep):
    from app.repositories.repositories import TeamRepository
    from app.models.team import Team
    repo = TeamRepository(session)
    teams = await repo.list(limit=50)
    teams.sort(key=lambda t: t.name)
    return [TeamSummary.model_validate(t) for t in teams]


@team_router.get("/{team_id}/roster", response_model=list[PlayerSummary])
async def get_team_roster(team_id: uuid.UUID, session: SessionDep):
    from app.repositories.repositories import PlayerRepository
    from app.models.player import Player
    repo = PlayerRepository(session)
    players = await repo.list(
        limit=60, filters=[Player.team_id == team_id, Player.active.is_(True)]
    )
    players.sort(key=lambda p: p.last_name)
    return [PlayerSummary.model_validate(p) for p in players]


# ── Stadiums ──────────────────────────────────────────────────────────────────

stadium_router = APIRouter(prefix="/stadiums", tags=["stadiums"])


@stadium_router.get("", response_model=list[StadiumResponse])
async def list_stadiums(session: SessionDep):
    repo = StadiumRepository(session)
    stadiums = await repo.list(limit=50)
    return [StadiumResponse.model_validate(s) for s in stadiums]


@stadium_router.get("/{stadium_id}", response_model=StadiumResponse)
async def get_stadium(stadium_id: uuid.UUID, session: SessionDep):
    repo = StadiumRepository(session)
    stadium = await repo.get_or_raise(stadium_id)
    return StadiumResponse.model_validate(stadium)


@stadium_router.get("/{stadium_id}/layout", response_model=StadiumLayoutResponse)
async def get_stadium_layout(stadium_id: uuid.UUID, session: SessionDep):
    from app.services.park_layout import build_layout
    repo = StadiumRepository(session)
    stadium = await repo.get_or_raise(stadium_id)
    return StadiumLayoutResponse(**build_layout(stadium))


# ── Ingest ────────────────────────────────────────────────────────────────────

ingest_router = APIRouter(prefix="/ingest", tags=["ingest"])

# Simple in-memory job tracker for prototype (replace with Redis/DB for production)
_jobs: dict[str, IngestJobStatus] = {}


@ingest_router.post("/players", response_model=IngestJobResponse)
async def trigger_player_ingest(
    background_tasks: BackgroundTasks,
    session: SessionDep,
    season: int = Query(default=2024),
):
    import uuid as _uuid
    from datetime import datetime, timezone

    job_id = str(_uuid.uuid4())
    now = datetime.now(timezone.utc)
    _jobs[job_id] = IngestJobStatus(
        job_id=job_id, status="pending", source="players",
        records_processed=0, errors=[], started_at=now,
    )

    async def _run():
        _jobs[job_id].status = "running"
        try:
            from app.services.ingest.ingest_services import PlayerIngestService
            svc = PlayerIngestService(session)
            count = await svc.ingest(season)
            _jobs[job_id].status = "complete"
            _jobs[job_id].records_processed = count
        except Exception as exc:
            _jobs[job_id].status = "failed"
            _jobs[job_id].errors.append(str(exc))

    background_tasks.add_task(_run)
    return IngestJobResponse(job_id=job_id, source="players", status="pending", started_at=now)


@ingest_router.post("/statcast", response_model=IngestJobResponse)
async def trigger_statcast_ingest(
    background_tasks: BackgroundTasks,
    session: SessionDep,
    start_date: str = Query(description="YYYY-MM-DD"),
    end_date: str = Query(description="YYYY-MM-DD"),
):
    import uuid as _uuid
    from datetime import datetime, timezone

    job_id = str(_uuid.uuid4())
    now = datetime.now(timezone.utc)
    _jobs[job_id] = IngestJobStatus(
        job_id=job_id,
        status="pending",
        source="statcast",
        records_processed=0,
        errors=[],
        started_at=now,
    )

    async def _run():
        _jobs[job_id].status = "running"
        try:
            from app.services.ingest.statcast import StatcastIngestService
            svc = StatcastIngestService(session)
            count = await svc.ingest(start_date, end_date)
            _jobs[job_id].status = "complete"
            _jobs[job_id].records_processed = count
        except Exception as exc:
            _jobs[job_id].status = "failed"
            _jobs[job_id].errors.append(str(exc))

    background_tasks.add_task(_run)
    return IngestJobResponse(job_id=job_id, source="statcast", status="pending", started_at=now)


@ingest_router.post("/fielding", response_model=IngestJobResponse)
async def trigger_fielding_ingest(
    background_tasks: BackgroundTasks,
    session: SessionDep,
    season: int = Query(default=2024),
):
    import uuid as _uuid
    from datetime import datetime, timezone

    job_id = str(_uuid.uuid4())
    now = datetime.now(timezone.utc)
    _jobs[job_id] = IngestJobStatus(
        job_id=job_id, status="pending", source="fielding",
        records_processed=0, errors=[], started_at=now,
    )

    async def _run():
        _jobs[job_id].status = "running"
        try:
            from app.services.ingest.fielding import FieldingIngestService
            svc = FieldingIngestService(session)
            count = await svc.ingest(season)
            _jobs[job_id].status = "complete"
            _jobs[job_id].records_processed = count
        except Exception as exc:
            _jobs[job_id].status = "failed"
            _jobs[job_id].errors.append(str(exc))

    background_tasks.add_task(_run)
    return IngestJobResponse(job_id=job_id, source="fielding", status="pending", started_at=now)


@ingest_router.get("/jobs/{job_id}", response_model=IngestJobStatus)
async def get_ingest_job(job_id: str):
    if job_id not in _jobs:
        raise NotFoundError("IngestJob", job_id)
    return _jobs[job_id]
