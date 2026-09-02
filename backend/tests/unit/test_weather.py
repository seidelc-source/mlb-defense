"""Unit tests for the deeper weather model: carry factor, trajectory-aware
shift, and manual-weather construction."""
from unittest.mock import MagicMock

from app.schemas.schemas import WeatherInput
from app.services.alignment.engine import _weather_shift, carry_factor
from app.services.weather_service import build_manual_weather, describe_weather


def _weather(temp=70.0, humidity=50.0, wind_x=0.0, wind_y=0.0):
    m = MagicMock()
    m.temperature_f = temp
    m.humidity_pct = humidity
    m.wind_x_component = wind_x
    m.wind_y_component = wind_y
    return m


class TestCarryFactor:
    def test_none_is_neutral(self):
        assert carry_factor(None) == 1.0

    def test_neutral_conditions(self):
        assert carry_factor(_weather(), 0.0) == 1.0

    def test_hot_air_carries_more(self):
        assert carry_factor(_weather(temp=95.0)) > 1.0

    def test_cold_air_carries_less(self):
        assert carry_factor(_weather(temp=40.0)) < 1.0

    def test_altitude_increases_carry(self):
        assert carry_factor(_weather(), altitude_ft=5200.0) > 1.0

    def test_wind_out_vs_in(self):
        assert carry_factor(_weather(wind_y=15.0)) > 1.0   # blowing out
        assert carry_factor(_weather(wind_y=-15.0)) < 1.0  # blowing in

    def test_clamped_to_range(self):
        extreme = carry_factor(_weather(temp=130.0, wind_y=60.0), altitude_ft=9000.0)
        assert extreme <= 1.20


class TestWeatherShift:
    def test_air_deepens_when_carrying(self):
        _, shift_y = _weather_shift(_weather(temp=95.0, wind_y=10.0), "air", 5200.0)
        assert shift_y > 0  # carry pushes fly balls deeper

    def test_ground_balls_unaffected_by_carry(self):
        _, shift_y = _weather_shift(_weather(temp=95.0, wind_y=10.0), "ground", 5200.0)
        assert shift_y == 0

    def test_ground_barely_moves_laterally(self):
        air_x, _ = _weather_shift(_weather(wind_x=20.0), "air", 0.0)
        ground_x, _ = _weather_shift(_weather(wind_x=20.0), "ground", 0.0)
        assert abs(ground_x) < abs(air_x)


class TestBuildManualWeather:
    def test_decomposes_wind_and_labels(self):
        w = build_manual_weather(None, WeatherInput(
            temperature_f=85, wind_speed_mph=12, wind_direction_deg=180, humidity_pct=40,
        ))
        assert w.game_id == "manual"
        assert w.temperature_f == 85
        assert w.wind_speed_mph == 12
        # wind from 180° (south) → blows out (+y) under the engine convention
        assert w.wind_y_component > 0
        assert w.wind_direction_label == "S"

    def test_describe_weather_reads_naturally(self):
        hot = build_manual_weather(None, WeatherInput(temperature_f=95, wind_speed_mph=15, wind_direction_deg=180))
        text = describe_weather(carry_factor(hot, 0.0), hot)
        assert "carr" in text.lower()
