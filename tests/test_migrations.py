import importlib.util
from pathlib import Path

import pytest

from dava.db import Database


def _load_migration_module(migration_filename: str):
    migrations_dir = Path(__file__).parent.parent / "scripts" / "migrations"
    filepath = migrations_dir / migration_filename
    module_name = f"scripts.migrations.{filepath.stem}"
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None:
        raise RuntimeError(f"Could not load spec for {module_name}")
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"Could not load loader for {module_name}")
    spec.loader.exec_module(module)
    return module


class TestMigration004VideoPromptDefault:
    def test_upgrade_replaces_exact_old_default(self, tmp_data_dir):
        db_path = tmp_data_dir / "mig004.db"
        db = Database(str(db_path), str(tmp_data_dir), admin_ids=set(), auto_create=True)
        try:
            old_default = "Animated portrait of a person centered in frame, {action}, {detailed_description}, {lighting_description}, {place}"
            db.set_global_default("video_prompt_text", old_default)

            mod = _load_migration_module("004_update_video_prompt_default.py")
            mod.upgrade(db)

            result = db.get_global_default("video_prompt_text")
            assert result == "{action}"
        finally:
            db._conn.close()

    def test_upgrade_leaves_custom_value_untouched(self, tmp_data_dir):
        db_path = tmp_data_dir / "mig004.db"
        db = Database(str(db_path), str(tmp_data_dir), admin_ids=set(), auto_create=True)
        try:
            custom = "my custom action only prompt {action} with extra"
            db.set_global_default("video_prompt_text", custom)

            mod = _load_migration_module("004_update_video_prompt_default.py")
            mod.upgrade(db)

            result = db.get_global_default("video_prompt_text")
            assert result == custom
        finally:
            db._conn.close()

    def test_downgrade_restores_old_when_current_is_new_default(self, tmp_data_dir):
        db_path = tmp_data_dir / "mig004.db"
        db = Database(str(db_path), str(tmp_data_dir), admin_ids=set(), auto_create=True)
        try:
            new_default = "{action}"
            db.set_global_default("video_prompt_text", new_default)

            mod = _load_migration_module("004_update_video_prompt_default.py")
            mod.downgrade(db)

            result = db.get_global_default("video_prompt_text")
            assert result == "Animated portrait of a person centered in frame, {action}, {detailed_description}, {lighting_description}, {place}"
        finally:
            db._conn.close()

    def test_downgrade_leaves_non_new_default_untouched(self, tmp_data_dir):
        db_path = tmp_data_dir / "mig004.db"
        db = Database(str(db_path), str(tmp_data_dir), admin_ids=set(), auto_create=True)
        try:
            custom = "some other prompt"
            db.set_global_default("video_prompt_text", custom)

            mod = _load_migration_module("004_update_video_prompt_default.py")
            mod.downgrade(db)

            result = db.get_global_default("video_prompt_text")
            assert result == custom
        finally:
            db._conn.close()


class TestMigration006StandardHolidayDates:
    def _db(self, tmp_data_dir):
        return Database(str(tmp_data_dir / "mig006.db"), str(tmp_data_dir), admin_ids=set(), auto_create=True)

    def test_upgrade_adds_missing_and_keeps_existing(self, tmp_data_dir):
        db = self._db(tmp_data_dir)
        try:
            db.set_global_default("holidays", {"07-30": "Birthday"})
            db.save_user_config(1, "holidays", {"10-31": "halloween", "01-02": "New Year's Day"})
            db.save_user_config(2, "holidays", {})

            mod = _load_migration_module("006_seed_standard_holiday_dates.py")
            mod.upgrade(db)

            glob = db.get_global_default("holidays")
            assert glob["07-30"] == "Birthday"
            assert glob["fri-13"] == "friday the 13th"
            assert glob["05-09"] == "Victory Day"
            assert list(glob)[0] == "07-30"  # existing rules stay first

            user1 = db.get_effective_value(1, "holidays")
            assert user1["10-31"] == "halloween"
            # Label already bound to a date — not duplicated.
            assert user1["01-02"] == "New Year's Day"
            assert "01-01" not in user1

            user2 = db.get_effective_value(2, "holidays")
            assert user2 == mod.STANDARD_HOLIDAYS
        finally:
            db._conn.close()

    def test_downgrade_removes_only_seeded(self, tmp_data_dir):
        db = self._db(tmp_data_dir)
        try:
            db.save_user_config(1, "holidays", {"10-31": "halloween"})
            mod = _load_migration_module("006_seed_standard_holiday_dates.py")
            mod.upgrade(db)
            mod.downgrade(db)

            assert db.get_effective_value(1, "holidays") == {"10-31": "halloween"}
            assert db.get_global_default("holidays") == {}
        finally:
            db._conn.close()
