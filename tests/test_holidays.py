from datetime import date
from unittest.mock import patch

import pytest

from dava.holidays import HolidayChecker, normalize_rule, rule_matches


@pytest.fixture
def today():
    with patch("dava.holidays.date") as mock_date:
        yield mock_date.today


class TestNormalizeRule:
    @pytest.mark.parametrize("text,expected", [
        ("10-31", "10-31"),
        (" 03-08 ", "03-08"),
        ("fri-13", "fri-13"),
        ("FRI-13", "fri-13"),
        ("mon-1", "mon-01"),
    ])
    def test_valid(self, text, expected):
        assert normalize_rule(text) == expected

    @pytest.mark.parametrize("text", ["", None, "13-01", "02-30x", "fr-13", "fri-32", "friday-13", "10/31"])
    def test_invalid(self, text):
        assert normalize_rule(text) is None


class TestRuleMatches:
    def test_month_day(self):
        assert rule_matches("10-31", date(2026, 10, 31))
        assert not rule_matches("10-31", date(2026, 10, 30))

    def test_weekday_day(self):
        assert rule_matches("fri-13", date(2026, 2, 13))  # Friday
        assert rule_matches("fri-13", date(2026, 3, 13))  # Friday
        assert not rule_matches("fri-13", date(2026, 2, 6))  # Friday, not 13th
        assert not rule_matches("fri-13", date(2026, 1, 13))  # Tuesday

    def test_invalid_rule_never_matches(self):
        assert not rule_matches("garbage", date(2026, 10, 31))


class TestGetTodayHoliday:
    def test_month_day_rule(self, today):
        today.return_value = date(2026, 10, 31)
        assert HolidayChecker().get_today_holiday({"10-31": "halloween"}) == "halloween"

    def test_weekday_rule(self, today):
        today.return_value = date(2026, 2, 13)
        assert HolidayChecker().get_today_holiday({"fri-13": "friday the 13th"}) == "friday the 13th"

    def test_first_match_wins(self, today):
        today.return_value = date(2026, 2, 13)
        holidays = {"02-13": "Birthday", "fri-13": "friday the 13th"}
        assert HolidayChecker().get_today_holiday(holidays) == "Birthday"
        reordered = {"fri-13": "friday the 13th", "02-13": "Birthday"}
        assert HolidayChecker().get_today_holiday(reordered) == "friday the 13th"

    def test_no_calendar_fallback(self, today):
        # Standard holidays come only from settings now.
        today.return_value = date(2026, 1, 1)
        assert HolidayChecker().get_today_holiday({}) is None
        assert HolidayChecker().get_today_holiday(None) is None


class TestGetClothing:
    def test_clothing_mentions_holiday(self):
        with patch.object(HolidayChecker, "get_today_holiday", return_value="Christmas"):
            assert HolidayChecker().get_clothing() == "clothing suitable for celebrating Christmas"


class TestGetDetails:
    def test_details_format(self):
        with patch.object(HolidayChecker, "get_today_holiday", return_value="Test Day"):
            assert HolidayChecker().get_details() == "everything is prepared for celebrating Test Day"
