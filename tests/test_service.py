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


class TestPreparePrompt:
    TEMPLATE = "Person in {place}. Wears {clothing}. Background: {environmental_details}."

    @pytest.fixture(autouse=True)
    def _setup(self, db_with_user):
        db_with_user.set_global_default("prompt_text", self.TEMPLATE)
        db_with_user.set_global_default("place", "Moscow")

    async def test_no_holiday_uses_default_clothing(self, service):
        service.holiday_checker.get_today_holiday = MagicMock(return_value=None)

        prompt = await service._prepare_prompt(1, {"environmental_details": "trees"})

        assert "{clothing}" not in prompt
        assert "Wears weather-appropriate clothing." in prompt

    async def test_holiday_without_action_uses_generic_clothing(self, service):
        service.holiday_checker.get_today_holiday = MagicMock(return_value="halloween")

        prompt = await service._prepare_prompt(1, {"environmental_details": "trees"})

        assert "Wears clothing suitable for celebrating halloween." in prompt
        assert "everything is prepared for celebrating halloween" in prompt
        assert "Holiday outfit and scene" not in prompt

    async def test_holiday_action_defines_outfit(self, service, db_with_user):
        action = "dressed in a pirate coat and tricorn hat"
        db_with_user.save_user_config(1, "video_actions", {"holidays": {"halloween": action}})
        service.holiday_checker.get_today_holiday = MagicMock(return_value="halloween")

        prompt = await service._prepare_prompt(1, {"environmental_details": "trees"})

        assert "clothing suitable for celebrating" not in prompt
        assert "Wears the holiday outfit described below." in prompt
        assert prompt.endswith("Holiday outfit and scene: " + action)

    async def test_apply_holidays_false_ignores_holiday(self, service, db_with_user):
        db_with_user.save_user_config(1, "video_actions", {"holidays": {"halloween": "pirate"}})
        service.holiday_checker.get_today_holiday = MagicMock(return_value="halloween")

        prompt = await service._prepare_prompt(1, {"environmental_details": "trees"}, apply_holidays=False)

        assert "pirate" not in prompt
        assert "Wears weather-appropriate clothing." in prompt


class TestHolidayDates:
    @pytest.mark.parametrize("raw,expected", [
        ("10-31", "10-31"), ("fri-13", "fri-13"), ("Fri-13", "fri-13"),
        ("-", ""), ("", ""), ("31-10", None), ("friday", None),
    ])
    def test_normalize_holiday_date(self, raw, expected):
        from dava.service import normalize_holiday_date
        assert normalize_holiday_date(raw) == expected

    def test_set_weekday_rule(self, service):
        assert service.set_holiday_date_for_name(1, "friday the 13th", "fri-13") is None
        assert service.get_holiday_date_for_name(1, "friday the 13th") == "fri-13"
