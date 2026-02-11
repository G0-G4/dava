from datetime import date

from workalendar.europe import Russia

from dava.config import Config

FRIDAY = "friday the 13th"

class HolidayChecker:

    def __init__(self, config: Config):
        self.config = config

    def get_today_holiday(self):
        day_month = '-'.join(str(date.today()).split('-')[1:])
        if self.config.holidays is not None and day_month in self.config.holidays:
            return self.config.holidays.get(day_month)
        if self.is_friday_13th():
            return FRIDAY
        return Russia().get_holiday_label(date.today())

    def get_clothing(self):
        holiday = self.get_today_holiday()
        if holiday == FRIDAY:
            "jason costume with mask and machete"
        return "clothing suitable for celebrating " + self.get_today_holiday()

    def get_details(self):
        return "everything is prepared for celebrating " + self.get_today_holiday()

    def is_friday_13th(self):
        today = date.today()
        return today.weekday() == 4 and today.day == 13


if __name__ == '__main__':
    config = Config()
    hc = HolidayChecker(config)
    print(hc.get_today_holiday())