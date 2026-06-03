from datetime import datetime
from unittest.mock import patch, AsyncMock

import pytest

from dava.weather_descriptor import WeatherDescriptor


@pytest.fixture
def wd():
    return WeatherDescriptor()


class TestGetForecast:
    async def test_weather_override(self, wd):
        override = {"description": "custom weather"}
        result = await wd.get_forecast(weather_override=override)
        assert result == override

    async def test_weather_override_with_code(self, wd):
        override = {"description": "custom weather", "weather_code": "95"}
        result = await wd.get_forecast(weather_override=override)
        assert result == override

    async def test_missing_coords_raises(self, wd):
        with pytest.raises(RuntimeError, match="latitude, longitude, and timezone are required"):
            await wd.get_forecast()

    async def test_partial_coords_raises(self, wd):
        with pytest.raises(RuntimeError):
            await wd.get_forecast(latitude=55.75)

    @patch("dava.weather_descriptor.make_request", new_callable=AsyncMock)
    async def test_api_response_day(self, mock_request, wd):
        mock_request.return_value = {
            "current": {"weather_code": 0, "is_day": 1}
        }
        with patch("dava.weather_descriptor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 6, 15)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = await wd.get_forecast(latitude=55.75, longitude=37.62, timezone="Europe/Moscow")
            assert "description" in result
            assert result["description"] == "Sunny"
            assert "weather_code" in result
            assert result["weather_code"] == "0"

    @patch("dava.weather_descriptor.make_request", new_callable=AsyncMock)
    async def test_api_response_night(self, mock_request, wd):
        mock_request.return_value = {
            "current": {"weather_code": 0, "is_day": 0}
        }
        with patch("dava.weather_descriptor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 6, 15)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = await wd.get_forecast(latitude=55.75, longitude=37.62, timezone="Europe/Moscow")
            assert result["description"] == "Clear Summer Night"
            assert result["weather_code"] == "0"


class TestSeasonMapping:
    @patch("dava.weather_descriptor.make_request", new_callable=AsyncMock)
    async def test_winter(self, mock_request, wd):
        mock_request.return_value = {"current": {"weather_code": 0, "is_day": 1}}
        with patch("dava.weather_descriptor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 15)
            result = await wd.get_forecast(latitude=1, longitude=1, timezone="UTC")
            assert result["description"] == "Sunny"

    @patch("dava.weather_descriptor.make_request", new_callable=AsyncMock)
    async def test_spring(self, mock_request, wd):
        mock_request.return_value = {"current": {"weather_code": 0, "is_day": 1}}
        with patch("dava.weather_descriptor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 4, 15)
            result = await wd.get_forecast(latitude=1, longitude=1, timezone="UTC")
            assert result["description"] == "Sunny"

    @patch("dava.weather_descriptor.make_request", new_callable=AsyncMock)
    async def test_autumn(self, mock_request, wd):
        mock_request.return_value = {"current": {"weather_code": 0, "is_day": 1}}
        with patch("dava.weather_descriptor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 10, 15)
            result = await wd.get_forecast(latitude=1, longitude=1, timezone="UTC")
            assert result["description"] == "Sunny"


class TestUnknownWeatherCode:
    @patch("dava.weather_descriptor.make_request", new_callable=AsyncMock)
    async def test_unknown_code_fallback(self, mock_request, wd):
        mock_request.return_value = {"current": {"weather_code": 999, "is_day": 1}}
        with patch("dava.weather_descriptor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 6, 15)
            result = await wd.get_forecast(latitude=1, longitude=1, timezone="UTC")
            assert "description" in result