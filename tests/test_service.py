from unittest.mock import AsyncMock, MagicMock

import pytest

from dava.errors import RequestError
from dava.service import DavaService


@pytest.fixture
def service(mock_config, db_with_user):
    updater = MagicMock()
    weather_descriptor = AsyncMock()
    return DavaService(mock_config, db_with_user, updater, weather_descriptor)


class TestGetWeather:
    async def test_success_cached(self, service, db_with_user):
        db_with_user.set_global_default("latitude", 55.7522)
        db_with_user.set_global_default("longitude", 37.6156)
        db_with_user.set_global_default("timezone", "Europe/Moscow")
        forecast = {"description": "Sunny", "weather_code": "0"}
        service.weather_descriptor.get_forecast.return_value = forecast

        result = await service._get_weather(1)

        assert result == forecast
        assert service._last_weather[1] == forecast
        service.weather_descriptor.get_forecast.assert_awaited_once()

    async def test_failure_logs_details_and_returns_none(self, service, db_with_user, caplog):
        db_with_user.set_global_default("latitude", 55.7522)
        db_with_user.set_global_default("longitude", 37.6156)
        db_with_user.set_global_default("timezone", "Europe/Moscow")
        service.weather_descriptor.get_forecast.side_effect = RequestError("Network error: timeout")

        with caplog.at_level("WARNING"):
            result = await service._get_weather(1)

        assert result is None
        assert "Could not fetch weather for user 1" in caplog.text
        assert "Network error: timeout" in caplog.text
        assert "55.7522" in caplog.text

    async def test_failure_returns_last_known_weather(self, service, db_with_user):
        db_with_user.set_global_default("latitude", 55.75)
        db_with_user.set_global_default("longitude", 37.62)
        db_with_user.set_global_default("timezone", "UTC")
        cached = {"description": "Sunny", "weather_code": "0"}
        service._last_weather[1] = cached
        service.weather_descriptor.get_forecast.side_effect = RequestError("Network error: timeout")

        result = await service._get_weather(1)

        assert result == cached
