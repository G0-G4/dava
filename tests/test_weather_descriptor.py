from datetime import datetime
from unittest.mock import patch, AsyncMock

import pytest

from dava.errors import RequestError
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

    async def test_weather_override_json_string(self, wd):
        override = '{"description": "custom weather", "weather_code": "95"}'
        result = await wd.get_forecast(weather_override=override)
        assert result == {"description": "custom weather", "weather_code": "95"}

    async def test_missing_coords_raises(self, wd):
        with pytest.raises(RuntimeError, match="latitude and longitude are required"):
            await wd.get_forecast()

    async def test_partial_coords_raises(self, wd):
        with pytest.raises(RuntimeError):
            await wd.get_forecast(latitude=55.75)

    @patch("dava.weather_descriptor.make_request", new_callable=AsyncMock)
    async def test_missing_timezone_uses_auto(self, mock_request, wd):
        mock_request.return_value = {"current": {"weather_code": 0, "is_day": 1}}
        await wd.get_forecast(latitude=55.75, longitude=37.62)
        assert mock_request.call_args.kwargs["params"]["timezone"] == "auto"

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


class TestRequestShape:
    @patch("dava.weather_descriptor.make_request", new_callable=AsyncMock)
    async def test_sends_user_agent_and_comma_separated_current(self, mock_request, wd):
        mock_request.return_value = {"current": {"weather_code": 0, "is_day": 1}}
        await wd.get_forecast(latitude="55.75", longitude="37,62", timezone=" Europe/Moscow ")
        kwargs = mock_request.call_args.kwargs
        assert kwargs["headers"]["User-Agent"].startswith("dava-dynamic-avatar")
        assert kwargs["params"]["current"] == "weather_code,is_day"
        assert kwargs["params"]["latitude"] == 55.75
        assert kwargs["params"]["longitude"] == 37.62
        assert kwargs["params"]["timezone"] == "Europe/Moscow"
        assert kwargs["timeout"] == 15


class TestRetries:
    @patch("dava.weather_descriptor.asyncio.sleep", new_callable=AsyncMock)
    @patch("dava.weather_descriptor.make_request", new_callable=AsyncMock)
    async def test_retries_network_error_then_succeeds(self, mock_request, mock_sleep, wd):
        mock_request.side_effect = [
            RequestError("Network error: timeout"),
            {"current": {"weather_code": 0, "is_day": 1}},
        ]
        result = await wd.get_forecast(latitude=1, longitude=1, timezone="UTC")
        assert result["weather_code"] == "0"
        assert mock_request.call_count == 2
        mock_sleep.assert_awaited_once()

    @patch("dava.weather_descriptor.asyncio.sleep", new_callable=AsyncMock)
    @patch("dava.weather_descriptor.make_request", new_callable=AsyncMock)
    async def test_retries_exhausted(self, mock_request, mock_sleep, wd):
        mock_request.side_effect = RequestError("Network error: timeout")
        with pytest.raises(RequestError, match="Network error"):
            await wd.get_forecast(latitude=1, longitude=1, timezone="UTC")
        assert mock_request.call_count == 3

    @patch("dava.weather_descriptor.make_request", new_callable=AsyncMock)
    async def test_invalid_timezone_falls_back_to_auto(self, mock_request, wd):
        mock_request.side_effect = [
            RequestError("GET https://api.open-meteo.com/v1/forecast failed: 400 - Invalid timezone"),
            {"current": {"weather_code": 0, "is_day": 1}},
        ]
        result = await wd.get_forecast(latitude=1, longitude=1, timezone="MSK")
        assert result["weather_code"] == "0"
        assert mock_request.call_args_list[0].kwargs["params"]["timezone"] == "MSK"
        assert mock_request.call_args_list[1].kwargs["params"]["timezone"] == "auto"

    @patch("dava.weather_descriptor.make_request", new_callable=AsyncMock)
    async def test_client_error_400_not_retried(self, mock_request, wd):
        mock_request.side_effect = RequestError(
            "GET https://api.open-meteo.com/v1/forecast failed: 400 - Latitude must be in range"
        )
        with pytest.raises(RequestError, match="400"):
            await wd.get_forecast(latitude=1, longitude=1, timezone="UTC")
        assert mock_request.call_count == 1

    @patch("dava.weather_descriptor.make_request", new_callable=AsyncMock)
    async def test_unexpected_response_raises(self, mock_request, wd):
        mock_request.return_value = {"error": True}
        with pytest.raises(RequestError, match="Unexpected Open-Meteo response"):
            await wd.get_forecast(latitude=1, longitude=1, timezone="UTC")