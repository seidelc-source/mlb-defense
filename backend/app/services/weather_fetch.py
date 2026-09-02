"""
WeatherFetchService — hourly job that fetches current weather for today's
games from the MLB Stats API schedule, then stores conditions via Open-Meteo.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.remaining_models import GameWeather
from app.repositories.repositories import StadiumRepository, WeatherRepository
from app.services.weather_service import WeatherService

logger = logging.getLogger(__name__)
settings = get_settings()


class WeatherFetchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.weather_svc = WeatherService(session)
        self.weather_repo = WeatherRepository(session)
        self.stadium_repo = StadiumRepository(session)

    async def fetch_todays_games(self) -> int:
        """
        Pull today's schedule from the MLB Stats API, then fetch weather
        for each game's stadium. Returns number of weather records upserted.
        """
        today = date.today()
        games = await self._get_schedule(today)

        if not games:
            logger.info("No games scheduled for %s", today)
            return 0

        count = 0
        for game in games:
            game_id = str(game.get("gamePk", ""))
            venue = game.get("venue", {})
            venue_id = str(venue.get("id", ""))

            if not game_id or not venue_id:
                continue

            existing = await self.weather_repo.get_by_game_id(game_id)
            if existing is not None:
                age = (datetime.now(timezone.utc) - existing.created_at).total_seconds()
                if age < 3600:
                    continue

            stadium = await self.stadium_repo.get_by_mlb_venue_id(venue_id)
            if stadium is None or stadium.latitude is None:
                logger.debug("Skipping game %s — no stadium coordinates for venue %s", game_id, venue_id)
                continue

            weather = await self.weather_svc._fetch_from_open_meteo(
                stadium, game_id=game_id, game_date=today
            )
            if weather is None:
                continue

            if existing is not None:
                existing.temperature_f = weather.temperature_f
                existing.humidity_pct = weather.humidity_pct
                existing.wind_speed_mph = weather.wind_speed_mph
                existing.wind_direction_deg = weather.wind_direction_deg
                existing.wind_direction_label = weather.wind_direction_label
                existing.wind_speed_level = weather.wind_speed_level
                existing.pressure_mb = weather.pressure_mb
                existing.conditions = weather.conditions
                existing.wind_x_component = weather.wind_x_component
                existing.wind_y_component = weather.wind_y_component
            else:
                self.session.add(weather)

            count += 1

        await self.session.flush()
        logger.info("Weather fetch complete: %d games updated for %s", count, today)
        return count

    async def _get_schedule(self, game_date: date) -> list[dict]:
        """Fetch today's games from the MLB Stats API."""
        url = (
            f"{settings.mlb_stats_api_base}/schedule"
            f"?sportId=1&date={game_date.isoformat()}"
            f"&hydrate=venue"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("MLB Stats API schedule request failed: %s", exc)
            return []

        games = []
        for date_entry in data.get("dates", []):
            for game in date_entry.get("games", []):
                venue = game.get("venue", {})
                games.append({
                    "gamePk": game.get("gamePk"),
                    "gameDate": game.get("gameDate"),
                    "status": game.get("status", {}).get("detailedState"),
                    "venue": venue,
                })
        return games
