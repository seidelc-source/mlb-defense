import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import NotFoundError
from app.repositories.repositories import (
    FieldingRepository,
    InjuryRepository,
    PitcherRepository,
    PlayerRepository,
)
from app.schemas.schemas import (
    FieldingProfileResponse,
    InjuryCreate,
    InjuryResponse,
    PitcherProfileResponse,
    PlayerDetailResponse,
    PlayerListResponse,
    PlayerSummary,
)
from app.services.injury_service import InjuryService

router = APIRouter(prefix="/players", tags=["players"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=PlayerListResponse)
async def list_players(
    session: SessionDep,
    name: str | None = Query(default=None, description="Partial name match"),
    position: str | None = Query(default=None),
    active: bool | None = Query(default=True),
    team_id: uuid.UUID | None = Query(default=None),
    role: str | None = Query(default=None, pattern="^(batter|pitcher)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> PlayerListResponse:
    repo = PlayerRepository(session)
    players, total = await repo.search(
        name=name,
        position=position,
        active=active,
        team_id=team_id,
        role=role,
        offset=offset,
        limit=limit,
    )
    return PlayerListResponse(
        total=total,
        players=[PlayerSummary.model_validate(p) for p in players],
    )


@router.get("/{player_id}", response_model=PlayerDetailResponse)
async def get_player(player_id: uuid.UUID, session: SessionDep) -> PlayerDetailResponse:
    repo = PlayerRepository(session)
    player = await repo.get_or_raise(player_id)
    return PlayerDetailResponse.model_validate(player)


@router.get("/{player_id}/fielding", response_model=list[FieldingProfileResponse])
async def get_fielding_profile(
    player_id: uuid.UUID,
    session: SessionDep,
    season: int = Query(default=2024, ge=2015),
    position: str | None = Query(default=None),
    apply_injuries: bool = Query(default=True),
) -> list[FieldingProfileResponse]:
    player_repo = PlayerRepository(session)
    fielding_repo = FieldingRepository(session)
    injury_svc = InjuryService(session)

    player = await player_repo.get_or_raise(player_id)
    profiles = await fielding_repo.get_profile(player_id, season, position)

    if not profiles:
        raise NotFoundError("FieldingProfile", f"{player_id}/{season}")

    player_summary = PlayerSummary.model_validate(player)
    results = []
    for profile in profiles:
        if apply_injuries:
            adjusted = await injury_svc.apply_for_player(profile)
            injuries_applied = adjusted.injuries_applied
            injury_adjusted = bool(injuries_applied)
        else:
            injuries_applied = []
            injury_adjusted = False

        results.append(
            FieldingProfileResponse(
                player=player_summary,
                season=profile.season,
                position=profile.position,
                games=profile.games,
                innings=profile.innings,
                sprint_speed_ft_s=adjusted.sprint_speed_ft_s if apply_injuries else profile.sprint_speed_ft_s,
                sprint_speed_level=adjusted.sprint_speed_level if apply_injuries else profile.sprint_speed_level,
                range_pct_vs_avg=adjusted.range_pct_vs_avg if apply_injuries else profile.range_pct_vs_avg,
                range_level=adjusted.range_level if apply_injuries else profile.range_level,
                reaction_time_s=adjusted.reaction_time_s if apply_injuries else profile.reaction_time_s,
                reaction_time_level=profile.reaction_time_level,
                route_efficiency_pct=profile.route_efficiency_pct,
                route_efficiency_level=profile.route_efficiency_level,
                arm_strength_mph=adjusted.arm_strength_mph if apply_injuries else profile.arm_strength_mph,
                arm_strength_level=adjusted.arm_strength_level if apply_injuries else profile.arm_strength_level,
                arm_accuracy_pct=adjusted.arm_accuracy_pct if apply_injuries else profile.arm_accuracy_pct,
                arm_accuracy_level=adjusted.arm_accuracy_level if apply_injuries else profile.arm_accuracy_level,
                actual_success_rate=profile.actual_success_rate,
                estimated_success_rate=profile.estimated_success_rate,
                diff_success_rate=profile.diff_success_rate,
                outs_above_average=profile.outs_above_average,
                oaa_back=profile.oaa_back,
                oaa_in=profile.oaa_in,
                oaa_left=profile.oaa_left,
                oaa_right=profile.oaa_right,
                fielding_run_value=profile.fielding_run_value,
                fielder_throwing_runs=profile.fielder_throwing_runs,
                injury_adjusted=injury_adjusted,
                injury_factors=None,
            )
        )
    return results


@router.get("/{player_id}/fielding/seasons", response_model=list[int])
async def get_fielding_seasons(player_id: uuid.UUID, session: SessionDep) -> list[int]:
    """Seasons with fielding data for this player (drives the UI dropdown)."""
    return await FieldingRepository(session).get_seasons(player_id)


@router.get("/{player_id}/pitching/seasons", response_model=list[int])
async def get_pitching_seasons(player_id: uuid.UUID, session: SessionDep) -> list[int]:
    """Seasons with pitcher data for this player (drives the UI dropdown)."""
    return await PitcherRepository(session).get_seasons(player_id)


@router.get("/{player_id}/pitching", response_model=PitcherProfileResponse)
async def get_pitching_profile(
    player_id: uuid.UUID,
    session: SessionDep,
    season: int = Query(default=2024, ge=2015),
) -> PitcherProfileResponse:
    player = await PlayerRepository(session).get_or_raise(player_id)
    profile = await PitcherRepository(session).get_profile(player_id, season)
    if profile is None:
        raise NotFoundError("PitcherProfile", f"{player_id}/{season}")

    return PitcherProfileResponse(
        player=PlayerSummary.model_validate(player),
        season=profile.season,
        role=profile.role,
        pitcher_type=profile.pitcher_type,
        groundball_pct=profile.groundball_pct,
        flyball_pct=profile.flyball_pct,
        linedrive_pct=profile.linedrive_pct,
        popup_pct=profile.popup_pct,
        strikeout_pct=profile.strikeout_pct,
        walk_pct=profile.walk_pct,
        avg_velocity_mph=profile.avg_velocity_mph,
        avg_fastball_mph=profile.avg_fastball_mph,
        max_fastball_mph=profile.max_fastball_mph,
        spin_rate_avg=profile.spin_rate_avg,
        pitch_mix=profile.pitch_mix,
    )


@router.get("/{player_id}/injury", response_model=list[InjuryResponse])
async def get_player_injuries(player_id: uuid.UUID, session: SessionDep):
    repo = PlayerRepository(session)
    await repo.get_or_raise(player_id)
    injury_repo = InjuryRepository(session)
    injuries = await injury_repo.get_active(player_id)
    return [InjuryResponse.model_validate(i) for i in injuries]


@router.post("/{player_id}/injury", response_model=InjuryResponse, status_code=201)
async def add_player_injury(
    player_id: uuid.UUID,
    body: InjuryCreate,
    session: SessionDep,
):
    from datetime import date as _date
    from app.schemas.schemas import INJURY_SEVERITY_PRESETS

    repo = PlayerRepository(session)
    await repo.get_or_raise(player_id)

    preset = INJURY_SEVERITY_PRESETS[body.severity]
    injury_repo = InjuryRepository(session)
    injury = await injury_repo.create(
        player_id=player_id,
        body_part=body.body_part,
        severity=body.severity,
        active=True,
        start_date=_date.today(),
        speed_factor=body.speed_factor if body.speed_factor is not None else preset["speed"],
        reaction_factor=body.reaction_factor if body.reaction_factor is not None else preset["reaction"],
        range_factor=body.range_factor if body.range_factor is not None else preset["range"],
        arm_strength_factor=body.arm_strength_factor if body.arm_strength_factor is not None else preset["arm_strength"],
        arm_accuracy_factor=body.arm_accuracy_factor if body.arm_accuracy_factor is not None else preset["arm_accuracy"],
        notes=body.notes,
    )
    return InjuryResponse.model_validate(injury)


@router.put("/{player_id}/injury/{injury_id}/end", response_model=InjuryResponse)
async def end_player_injury(
    player_id: uuid.UUID,
    injury_id: uuid.UUID,
    session: SessionDep,
):
    from datetime import date as _date

    injury_repo = InjuryRepository(session)
    injury = await injury_repo.get_or_raise(injury_id)
    if injury.player_id != player_id:
        raise NotFoundError("PlayerInjury", injury_id)
    injury = await injury_repo.update(injury, active=False, end_date=_date.today())
    return InjuryResponse.model_validate(injury)
