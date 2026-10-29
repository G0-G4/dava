import re
from datetime import date

# Holiday date rules (keys of the ``holidays`` config map):
#   "MM-DD"  — fixed calendar day, e.g. "10-31"
#   "ddd-DD" — weekday + day of month, e.g. "fri-13"
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

_MONTH_DAY_RE = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
_WEEKDAY_DAY_RE = re.compile(r"^(" + "|".join(WEEKDAYS) + r")-(0?[1-9]|[12]\d|3[01])$")


def normalize_rule(text: str | None) -> str | None:
    """Return a canonical holiday date rule, or None if ``text`` is not one."""
    rule = (text or "").strip().lower()
    if _MONTH_DAY_RE.match(rule):
        return rule
    match = _WEEKDAY_DAY_RE.match(rule)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    return None


def rule_matches(rule: str, day: date) -> bool:
    rule = normalize_rule(rule)
    if rule is None:
        return False
    head, tail = rule.split("-")
    if head in WEEKDAYS:
        return day.weekday() == WEEKDAYS.index(head) and day.day == int(tail)
    return day.month == int(head) and day.day == int(tail)


class HolidayChecker:

    def get_today_holiday(self, holidays: dict | None = None) -> str | None:
        """Return the label of the first rule in ``holidays`` matching today."""
        today = date.today()
        for rule, label in (holidays or {}).items():
            if rule_matches(rule, today):
                return label
        return None

    def get_clothing(self, holidays: dict | None = None):
        return "clothing suitable for celebrating " + self.get_today_holiday(holidays)

    def get_details(self, holidays: dict | None = None):
        return "everything is prepared for celebrating " + self.get_today_holiday(holidays)


if __name__ == '__main__':
    hc = HolidayChecker()
    print(hc.get_today_holiday())
