"""Bind standard holiday labels to explicit date rules.

Holidays used to be detected via workalendar (Russia) plus a hardcoded
Friday 13th rule. Detection is now driven only by the ``holidays`` config
map (date rule → label), so the labels used by the seeded video_actions
need explicit dates. Existing bindings are never overwritten: a label that
already has a date, or a rule that is already taken, is skipped.
"""

import json

STANDARD_HOLIDAYS = {
    "01-01": "New Year's Day",
    "01-07": "Orthodox Christmas Day",
    "02-23": "Defender of the Fatherland Day",
    "03-08": "International Women's Day",
    "05-01": "Spring and Labour Day",
    "05-09": "Victory Day",
    "06-12": "National Day",
    "11-04": "Unity Day",
    "12-25": "Christmas Day",
    "fri-13": "friday the 13th",
}


def _with_standard(holidays: dict) -> dict:
    result = dict(holidays)
    labels = set(result.values())
    for rule, label in STANDARD_HOLIDAYS.items():
        if label in labels or rule in result:
            continue
        result[rule] = label
    return result


def _without_standard(holidays: dict) -> dict:
    return {
        rule: label for rule, label in holidays.items()
        if STANDARD_HOLIDAYS.get(rule) != label
    }


def _apply(db, transform):
    current = db.get_global_default("holidays")
    db.set_global_default("holidays", transform(current if isinstance(current, dict) else {}))

    rows = db._conn.execute(
        "SELECT user_id, value FROM user_config WHERE key = 'holidays'"
    ).fetchall()
    for row in rows:
        value = json.loads(row["value"])
        if isinstance(value, dict):
            db.save_user_config(row["user_id"], "holidays", transform(value))


def upgrade(db):
    _apply(db, _with_standard)


def downgrade(db):
    _apply(db, _without_standard)
