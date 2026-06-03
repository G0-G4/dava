import os

from dava.config import ALL_CONFIGURABLE_KEYS, convert_value

ENV_MIGRATABLE_KEYS = ALL_CONFIGURABLE_KEYS


def upgrade(db):
    for key in ENV_MIGRATABLE_KEYS:
        raw = os.getenv(key)
        if raw is not None:
            try:
                value = convert_value(key, raw)
                db.set_global_default(key, value, skip_if_exists=True)
            except Exception:
                pass


def downgrade(db):
    pass