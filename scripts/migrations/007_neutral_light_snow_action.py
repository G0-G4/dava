"""Replace the light-snow video action that catches snowflakes on the tongue.

Weather code 71 ("Light Snow") asked the video model to show the person
catching snowflakes on their tongue. Swap that for catching them with
their hands, in the global default and in any user copy that still has
the original sentence. Custom wording is left as-is.
"""

import json

OLD_LIGHT_SNOW = (
    "gentle snowfall, snowflakes drifting softly in the air as user "
    "catches snowflakes on their tongue, looking up with wonder"
)
NEW_LIGHT_SNOW = (
    "gentle snowfall, snowflakes drifting softly in the air as user "
    "catches snowflakes with their hands, looking up with wonder"
)


def _swap(actions, source, target):
    if not isinstance(actions, dict):
        return actions, False
    weather = actions.get("weather")
    if not isinstance(weather, dict) or weather.get("71") != source:
        return actions, False
    updated = dict(actions)
    updated["weather"] = dict(weather)
    updated["weather"]["71"] = target
    return updated, True


def _apply(db, source, target):
    current = db.get_global_default("video_actions")
    updated, changed = _swap(current, source, target)
    if changed:
        db.set_global_default("video_actions", updated)

    rows = db._conn.execute(
        "SELECT user_id, value FROM user_config WHERE key = ?",
        ("video_actions",),
    ).fetchall()
    for row in rows:
        value = json.loads(row["value"])
        updated, changed = _swap(value, source, target)
        if changed:
            db.save_user_config(row["user_id"], "video_actions", updated)


def upgrade(db):
    _apply(db, OLD_LIGHT_SNOW, NEW_LIGHT_SNOW)


def downgrade(db):
    _apply(db, NEW_LIGHT_SNOW, OLD_LIGHT_SNOW)
