from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from dava.holidays import HolidayChecker, FRIDAY


class TestIsFriday13th:
    def test_friday_13th_true(self):
        hc = HolidayChecker()
        with patch("dava.holidays.date") as mock_date:
            mock_date.today.return_value = date(2025, 6, 13)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            assert hc.is_friday_13th() is True

    def test_friday_13th_false_non_friday(self):
        hc = HolidayChecker()
        with patch("dava.holidays.date") as mock_date:
            mock_date.today.return_value = date(2025, 6, 14)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            assert hc.is_friday_13th() is False

    def test_friday_13th_false_not_13th(self):
        hc = HolidayChecker()
        with patch("dava.holidays.date") as mock_date:
            mock_date.today.return_value = date(2025, 6, 6)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            assert hc.is_friday_13th() is False


class TestGetTodayHoliday:
    def test_custom_override(self):
        hc = HolidayChecker()
        holidays = {"01-01": "New Year"}
        with patch("dava.holidays.date") as mock_date:
            mock_date.today.return_value = date(2025, 1, 1)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            result = hc.get_today_holiday(holidays=holidays)
            assert result == "New Year"

    def test_friday_13th(self):
        hc = HolidayChecker()
        with patch.object(HolidayChecker, 'is_friday_13th', return_value=True):
            result = hc.get_today_holiday()
            assert result == FRIDAY

    def test_russian_holiday(self):
        hc = HolidayChecker()
        with patch.object(HolidayChecker, 'is_friday_13th', return_value=False):
            with patch("dava.holidays.Russia") as MockRussia:
                mock_cal = MagicMock()
                mock_cal.get_holiday_label.return_value = "New Year"
                MockRussia.return_value = mock_cal
                result = hc.get_today_holiday()
                assert result == "New Year"


class TestGetClothing:
    def test_friday_13th_clothing(self):
        hc = HolidayChecker()
        with patch.object(HolidayChecker, 'get_today_holiday', return_value=FRIDAY):
            result = hc.get_clothing()
            assert result == "jason costume with mask and machete"

    def test_normal_holiday_clothing(self):
        hc = HolidayChecker()
        with patch.object(HolidayChecker, 'get_today_holiday', return_value="Christmas"):
            result = hc.get_clothing()
            assert "Christmas" in result
            assert "clothing suitable" in result


class TestGetDetails:
    def test_details_format(self):
        hc = HolidayChecker()
        with patch.object(HolidayChecker, 'get_today_holiday', return_value="Test Day"):
            result = hc.get_details()
            assert result == "everything is prepared for celebrating Test Day"