#!/usr/bin/env python3
"""Database migration runner.

Discovers migration scripts in scripts/migrations/, runs any that
haven't been applied yet, and records them in the schema_version table.

Usage:
    uv run scripts/run_migrations.py
"""

import importlib
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def discover_migrations():
    migrations = []
    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        match = re.match(r"^(\d+)_.+\.py$", path.name)
        if match:
            migrations.append((int(match.group(1)), path.name, path))
    return sorted(migrations, key=lambda x: x[0])


def get_applied(db):
    rows = db._conn.execute(
        "SELECT migration FROM schema_version ORDER BY id"
    ).fetchall()
    return {row["migration"] for row in rows}


def run_migrations():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from dava.config import Config
    from dava.db import Database

    config = Config()
    from pathlib import Path as P
    data_dir = P(config.data_dir)
    db = Database(data_dir / "bot.db", data_dir, admin_ids=set(config.admin_chat_ids), auto_create=True)

    db._conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration TEXT NOT NULL UNIQUE,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db._conn.commit()

    applied = get_applied(db)
    migrations = discover_migrations()

    for number, filename, filepath in migrations:
        if filename in applied:
            logger.info(f"Migration {number:03d} ({filename}) already applied, skipping")
            continue

        module_name = f"scripts.migrations.{filepath.stem}"
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        logger.info(f"Running migration {number:03d} ({filename})")
        module.upgrade(db)

        db._conn.execute(
            "INSERT INTO schema_version (migration) VALUES (?)",
            (filename,),
        )
        db._conn.commit()
        logger.info(f"Migration {number:03d} ({filename}) applied")

    db._conn.close()
    logger.info("All migrations applied")


if __name__ == "__main__":
    run_migrations()