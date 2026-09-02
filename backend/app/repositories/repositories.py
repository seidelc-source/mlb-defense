"""
All repositories in one file for the scaffold.
Each class handles a specific ORM model.
"""
import uuid
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.models.fielding_profile import FieldingProfile
from app.models.pitcher_profile import PitcherProfile
from app.models.player import Player
from app.models.remaining_models import (
    BatterSprayProfile,
    DefensiveAlignment,
    GameWeather,
    PlayerInjury,
)
from app.models.stadium import Stadium
from app.models.team import Team
from app.repositories.base import BaseRepository


class TeamRepository(BaseRepository[Team]):
    model = Team

    async def get_by_mlb_team_id(self, mlb_team_id: str) -> Team | None:
        stmt = select(Team).where(Team.mlb_team_id == mlb_team_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class PlayerRepository(BaseRepository[Player]):
    model = Player

    async def get_by_mlbam_id(self, mlbam_id: str) -> Player | None:
        stmt = select(Player).where(Player.mlbam_id == mlbam_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(
        self,
        name: str | None = None,
        position: str | None = None,
        active: bool | None = None,
        team_id: uuid.UUID | None = None,
        role: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Player], int]:
        filters: list[Any] = []
        if name:
            filters.append(Player.full_name.ilike(f"%{name}%"))
        if position:
            filters.append(Player.position == position.upper())
        if active is not None:
            filters.append(Player.active == active)
        if team_id:
            filters.append(Player.team_id == team_id)
        if role == "pitcher":
            filters.append(Player.position == "P")
        elif role == "batter":
            filters.append(Player.position != "P")

        players = await self.list(offset=offset, limit=limit, filters=filters or None)
        total = await self.count(filters=filters or None)
        return players, total

    async def get_with_injuries(self, player_id: uuid.UUID) -> Player | None:
        stmt = (
            select(Player)
            .options(selectinload(Player.injuries))
            .where(Player.id == player_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class FieldingRepository(BaseRepository[FieldingProfile]):
    model = FieldingProfile

    async def get_seasons(self, player_id: uuid.UUID) -> list[int]:
        """Seasons that actually have fielding data for this player, newest first."""
        stmt = (
            select(FieldingProfile.season)
            .where(FieldingProfile.player_id == player_id)
            .distinct()
            .order_by(FieldingProfile.season.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_profile(
        self, player_id: uuid.UUID, season: int, position: str | None = None
    ) -> list[FieldingProfile]:
        filters: list[Any] = [
            FieldingProfile.player_id == player_id,
            FieldingProfile.season == season,
        ]
        if position:
            filters.append(FieldingProfile.position == position.upper())
        stmt = select(FieldingProfile).where(and_(*filters))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_profile(
        self, player_id: uuid.UUID, position: str | None = None
    ) -> FieldingProfile | None:
        filters: list[Any] = [FieldingProfile.player_id == player_id]
        if position:
            filters.append(FieldingProfile.position == position.upper())
        stmt = (
            select(FieldingProfile)
            .where(and_(*filters))
            .order_by(FieldingProfile.season.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class PitcherRepository(BaseRepository[PitcherProfile]):
    model = PitcherProfile

    async def get_profile(
        self, player_id: uuid.UUID, season: int
    ) -> PitcherProfile | None:
        stmt = select(PitcherProfile).where(
            and_(
                PitcherProfile.player_id == player_id,
                PitcherProfile.season == season,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_profile(
        self, player_id: uuid.UUID
    ) -> PitcherProfile | None:
        stmt = (
            select(PitcherProfile)
            .where(PitcherProfile.player_id == player_id)
            .order_by(PitcherProfile.season.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_seasons(self, player_id: uuid.UUID) -> list[int]:
        """Seasons that actually have pitcher data for this player, newest first."""
        stmt = (
            select(PitcherProfile.season)
            .where(PitcherProfile.player_id == player_id)
            .distinct()
            .order_by(PitcherProfile.season.desc())
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]


class SprayRepository(BaseRepository[BatterSprayProfile]):
    model = BatterSprayProfile

    async def get_seasons(self, player_id: uuid.UUID) -> list[int]:
        """Seasons that actually have spray data for this player, newest first."""
        stmt = (
            select(BatterSprayProfile.season)
            .where(BatterSprayProfile.player_id == player_id)
            .distinct()
            .order_by(BatterSprayProfile.season.desc())
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_zones(
        self,
        player_id: uuid.UUID,
        season: int | None,
        pitch_type: str | None = None,
        pitcher_hand: str | None = None,
        speed_min: float | None = None,
        speed_max: float | None = None,
    ) -> list[BatterSprayProfile]:
        """Return all zone rows for the given scenario, null-safe on optional
        filters. season=None returns rows across all seasons."""
        filters: list[Any] = [BatterSprayProfile.player_id == player_id]
        if season is not None:
            filters.append(BatterSprayProfile.season == season)
        if pitch_type is not None:
            filters.append(BatterSprayProfile.pitch_type == pitch_type)
        else:
            filters.append(BatterSprayProfile.pitch_type.is_(None))
        if pitcher_hand is not None:
            filters.append(BatterSprayProfile.pitcher_hand == pitcher_hand)
        else:
            filters.append(BatterSprayProfile.pitcher_hand.is_(None))
        if speed_min is not None:
            filters.append(BatterSprayProfile.pitch_speed_min == speed_min)
        else:
            filters.append(BatterSprayProfile.pitch_speed_min.is_(None))
        if speed_max is not None:
            filters.append(BatterSprayProfile.pitch_speed_max == speed_max)
        else:
            filters.append(BatterSprayProfile.pitch_speed_max.is_(None))

        stmt = select(BatterSprayProfile).where(and_(*filters)).order_by(
            BatterSprayProfile.fielding_zone
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class StadiumRepository(BaseRepository[Stadium]):
    model = Stadium

    async def get_by_mlb_venue_id(self, mlb_venue_id: str) -> Stadium | None:
        stmt = select(Stadium).where(Stadium.mlb_venue_id == mlb_venue_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class AlignmentRepository(BaseRepository[DefensiveAlignment]):
    model = DefensiveAlignment

    async def get_history(
        self,
        batter_id: uuid.UUID | None = None,
        pitcher_id: uuid.UUID | None = None,
        team_id: uuid.UUID | None = None,
        season: int | None = None,
        limit: int = 20,
    ) -> list[DefensiveAlignment]:
        filters: list[Any] = []
        if batter_id:
            filters.append(DefensiveAlignment.batter_id == batter_id)
        if pitcher_id:
            filters.append(DefensiveAlignment.pitcher_id == pitcher_id)
        if team_id:
            filters.append(DefensiveAlignment.team_id == team_id)
        stmt = (
            select(DefensiveAlignment)
            .where(and_(*filters) if filters else True)
            .order_by(DefensiveAlignment.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class WeatherRepository(BaseRepository[GameWeather]):
    model = GameWeather

    async def get_by_game_id(self, game_id: str) -> GameWeather | None:
        stmt = (
            select(GameWeather)
            .where(GameWeather.game_id == game_id)
            .order_by(GameWeather.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_latest_live(self, stadium_id: uuid.UUID) -> GameWeather | None:
        stmt = (
            select(GameWeather)
            .where(
                GameWeather.game_id == "live",
                GameWeather.stadium_id == stadium_id,
            )
            .order_by(GameWeather.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()


class InjuryRepository(BaseRepository[PlayerInjury]):
    model = PlayerInjury

    async def get_active(self, player_id: uuid.UUID) -> list[PlayerInjury]:
        stmt = select(PlayerInjury).where(
            and_(PlayerInjury.player_id == player_id, PlayerInjury.active.is_(True))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
