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
