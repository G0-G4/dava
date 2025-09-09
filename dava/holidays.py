from datetime import date, timedelta

from workalendar.europe import Russia

from dava.config import Config


class HolidayChecker:

    def __init__(self, config: Config):
        self.config = config

    def get_today_holiday(self):
        day_month = '-'.join(str(date.today()).split('-')[1:])
        if self.config.holidays is not None and day_month in self.config.holidays:
            return self.config.holidays.get(day_month)
        return Russia().get_holiday_label(date.today())

if __name__ == '__main__':
    config = Config()
    hc = HolidayChecker(config)
    print(hc.get_today_holiday())