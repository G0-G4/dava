from datetime import date

from workalendar.europe import Russia

FRIDAY = "friday the 13th"


class HolidayChecker:

    def get_today_holiday(self, holidays: dict | None = None):
        if holidays is not None:
            day_month = '-'.join(str(date.today()).split('-')[1:])
            if day_month in holidays:
                return holidays.get(day_month)
        if self.is_friday_13th():
            return FRIDAY
        return Russia().get_holiday_label(date.today())

    def get_clothing(self, holidays: dict | None = None):
        holiday = self.get_today_holiday(holidays)
        if holiday == FRIDAY:
            return "jason costume with mask and machete"
        return "clothing suitable for celebrating " + holiday

    def get_details(self, holidays: dict | None = None):
        return "everything is prepared for celebrating " + self.get_today_holiday(holidays)

    def is_friday_13th(self):
        today = date.today()
        return today.weekday() == 4 and today.day == 13


if __name__ == '__main__':
    hc = HolidayChecker()
    print(hc.get_today_holiday())