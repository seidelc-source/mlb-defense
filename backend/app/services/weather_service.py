"""
WeatherService fetches game weather from Open-Meteo and decomposes wind
into field-coordinate components used by the alignment engine.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.models.remaining_models import GameWeather
from app.models.stadium import Stadium
from app.repositories.repositories import StadiumRepository, WeatherRepository

logger = logging.getLogger(__name__)
settings = get_settings()

# Wind direction labels: 0=N, 45=NE, 90=E, 135=SE, 180=S, 225=SW, 270=W, 315=NW
_DIR_LABELS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# Open-Meteo weather codes → simple condition labels
_WMO_CONDITIONS: dict[int, str] = {
    0: "clear", 1: "clear", 2: "partly_cloudy", 3: "cloudy",
    45: "fog", 48: "fog",
    51: "drizzle", 53: "drizzle", 55: "drizzle",
    61: "rain", 63: "rain", 65: "rain",
    71: "snow", 73: "snow", 75: "snow",
    80: "showers", 81: "showers", 82: "showers",
    95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm",
}


def _wind_direction_label(deg: float) -> str:
    idx = round(deg / 45) % 8
    return _DIR_LABELS[idx]


def _wind_speed_level(mph: float) -> int:
    """Paper's Table 1 wind speed levels."""
    if mph <= 5:
        return 1
    if mph <= 10:
        return 2
    if mph <= 15:
        return 3
    if mph <= 20:
        return 4
    return 5


def _decompose_wind(speed_mph: float, direction_deg: float) -> tuple[float, float]:
    """
    Decompose wind into field components.
    Assumes home plate faces south (most common MLB orientation).
    x_component: positive = blowing toward right field
    y_component: positive = blowing toward outfield (helping fly balls)
    """
    rad = math.radians(direction_deg)
    # Wind direction is where wind comes FROM; field_from means ball pushed opposite
    x = -speed_mph * math.sin(rad)   # east-west component
    y = -speed_mph * math.cos(rad)   # in-out component
    return round(x, 2), round(y, 2)


def build_manual_weather(stadium_id, params) -> GameWeather:
    """Construct an unsaved GameWeather from manual/override inputs (a
    WeatherInput), computing the derived wind components/labels the engine and
    UI need. Not added to any session — purely for in-request use."""
    wind = params.wind_speed_mph or 0.0
    deg = params.wind_direction_deg if params.wind_direction_deg is not None else 0.0
    x_comp, y_comp = _decompose_wind(wind, deg)
    return GameWeather(
        game_id="manual",
        stadium_id=stadium_id,
        game_date=date.today(),
        temperature_f=params.temperature_f,
        humidity_pct=params.humidity_pct,
        wind_speed_mph=wind,
        wind_direction_deg=deg,
        wind_direction_label=_wind_direction_label(deg),
        wind_speed_level=_wind_speed_level(wind),
        conditions=params.conditions,
        wind_x_component=x_comp,
        wind_y_component=y_comp,
    )


def describe_weather(carry: float, weather: GameWeather) -> str:
    """One-line plain-English summary of how conditions bend batted balls."""
    pct = (carry - 1.0) * 100
    if pct >= 4:
        carry_txt = f"carries well (+{pct:.0f}%)"
    elif pct >= 1.5:
        carry_txt = f"slight carry (+{pct:.0f}%)"
    elif pct <= -4:
        carry_txt = f"knocks balls down ({pct:.0f}%)"
    elif pct <= -1.5:
        carry_txt = f"slightly suppressed ({pct:.0f}%)"
    else:
        carry_txt = "neutral carry"

    wx = weather.wind_x_component or 0.0
    drift = ", drift to RF" if wx > 2 else ", drift to LF" if wx < -2 else ""
    return carry_txt[0].upper() + carry_txt[1:] + drift


class WeatherService:
    def __init__(self, session: AsyncSession) -> None:
        self.weather_repo = WeatherRepository(session)
        self.stadium_repo = StadiumRepository(session)

    async def get_for_game(self, game_id: str) -> GameWeather | None:
        return await self.weather_repo.get_by_game_id(game_id)

    async def fetch_current(self, stadium_id) -> GameWeather | None:
        """Current conditions for a stadium (by row UUID), persisted and
        reused for 30 minutes to avoid hammering Open-Meteo."""
        stadium = await self.stadium_repo.get(stadium_id)
        if stadium is None or stadium.latitude is None:
            logger.warning("Cannot fetch weather — stadium %s has no coordinates", stadium_id)
            return None

        recent = await self.weather_repo.get_latest_live(stadium.id)
        if recent is not None and recent.created_at is not None:
            age = datetime.now(timezone.utc) - recent.created_at
            if age < timedelta(minutes=30):
                return recent

        weather = await self._fetch_from_open_meteo(
            stadium, game_id="live", game_date=date.today()
        )
        if weather is not None:
            self.weather_repo.session.add(weather)
            await self.weather_repo.session.flush()
        return weather

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _fetch_from_open_meteo(
        self, stadium: Stadium, game_id: str, game_date: date
    ) -> GameWeather | None:
        url = (
            f"{settings.open_meteo_base}/forecast"
            f"?latitude={stadium.latitude}"
            f"&longitude={stadium.longitude}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,"
            f"wind_direction_10m,surface_pressure,weather_code"
            f"&wind_speed_unit=mph"
            f"&temperature_unit=fahrenheit"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("Open-Meteo request failed: %s", exc)
            return None

        current = data.get("current", {})
        temp_f = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")
        wind_mph = current.get("wind_speed_10m", 0.0)
        wind_deg = current.get("wind_direction_10m", 0.0)
        wmo_code = current.get("weather_code", 0)
        pressure = current.get("surface_pressure")

        x_comp, y_comp = _decompose_wind(wind_mph or 0.0, wind_deg or 0.0)

        weather = GameWeather(
            game_id=game_id,
            stadium_id=stadium.id,
            game_date=game_date,
            temperature_f=temp_f,
            humidity_pct=humidity,
            wind_speed_mph=wind_mph,
            wind_direction_deg=wind_deg,
            wind_direction_label=_wind_direction_label(wind_deg or 0.0),
            wind_speed_level=_wind_speed_level(wind_mph or 0.0),
            pressure_mb=pressure,
            conditions=_WMO_CONDITIONS.get(wmo_code, "unknown"),
            wind_x_component=x_comp,
            wind_y_component=y_comp,
        )
        return weather
