import json
from pathlib import Path

import pytest

from dava.db import Database


class TestDatabaseInit:
    def test_creates_tables(self, tmp_data_dir):
        db_path = tmp_data_dir / "test.db"
        db = Database(str(db_path), str(tmp_data_dir))
        cursor = db._conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        db._conn.close()
        assert "users" in tables
        assert "user_config" in tables
        assert "global_config" in tables

    def test_creates_data_dirs(self, tmp_path):
        data_dir = tmp_path / "new_data"
        data_dir.mkdir()
        db_path = data_dir / "test.db"
        db = Database(str(db_path), str(data_dir))
        assert data_dir.exists()
        assert (data_dir / "users").exists()
        db._conn.close()


class TestUserManagement:
    def test_ensure_user_creates_row(self, db):
        db.ensure_user(1)
        row = db._conn.execute("SELECT user_id FROM users WHERE user_id = 1").fetchone()
        assert row is not None
        assert row["user_id"] == 1

    def test_ensure_user_idempotent(self, db):
        db.ensure_user(1)
        db.ensure_user(1)
        rows = db._conn.execute("SELECT COUNT(*) as cnt FROM users WHERE user_id = 1").fetchone()
        assert rows["cnt"] == 1

    def test_user_exists_true(self, db_with_user):
        assert db_with_user.user_exists(1) is True

    def test_user_exists_false(self, db):
        assert db.user_exists(999) is False

    def test_is_admin(self, db):
        assert db.is_admin(111) is True
        assert db.is_admin(222) is True
        assert db.is_admin(999) is False

    def test_is_allowed_admin_implicit(self, db):
        assert db.is_allowed(111) is True

    def test_is_allowed_non_admin_not_allowed(self, db):
        assert db.is_allowed(999) is False

    def test_grant(self, db):
        db.grant(5)
        assert db.is_allowed(5) is True

    def test_revoke(self, db):
        db.grant(5)
        db.revoke(5)
        assert db.is_allowed(5) is False

    def test_list_allowed_includes_admins(self, db):
        allowed = db.list_allowed()
        assert 111 in allowed
        assert 222 in allowed

    def test_list_allowed_includes_granted(self, db):
        db.grant(5)
        allowed = db.list_allowed()
        assert 5 in allowed

    def test_list_users(self, db_with_user):
        user_ids = db_with_user.list_users()
        assert 1 in user_ids


class TestConnections:
    def test_save_and_load_connection(self, db):
        db.save_connection(1, "conn-123", 456, {"edit_profile_photo": True})
        result = db.load_connection(1)
        assert result is not None
        assert result["connection_id"] == "conn-123"
        assert result["user_id"] == 456
        assert result["rights"]["edit_profile_photo"] is True

    def test_load_connection_none(self, db):
        result = db.load_connection(999)
        assert result is None

    def test_save_connection_no_rights(self, db):
        db.save_connection(1, "conn-abc", 789)
        result = db.load_connection(1)
        assert result["connection_id"] == "conn-abc"
        assert result["rights"]["edit_profile_photo"] is False


class TestBaseImage:
    def test_save_base_image(self, db):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake image data")
            src = Path(f.name)
        try:
            db.ensure_user(1)
            result = db.save_base_image(1, src)
            assert db.has_base_image(1) is True
            assert db.get_base_image_path(1) == result
        finally:
            src.unlink(missing_ok=True)

    async def test_save_base_image_bytes(self, db):
        db.ensure_user(1)
        result = await db.save_base_image_bytes(1, b"fake image data")
        assert db.has_base_image(1) is True
        assert Path(result).exists()

    def test_has_base_image_false(self, db):
        assert db.has_base_image(999) is False

    def test_get_base_image_path_none(self, db):
        assert db.get_base_image_path(999) is None

    def test_get_base_image_path_fallback(self, db, tmp_data_dir):
        db.ensure_user(1)
        fallback = tmp_data_dir / "users" / "1" / "avatar.jpg"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_bytes(b"image")
        path = db.get_base_image_path(1)
        assert path == str(fallback)


class TestGlobalConfig:
    def test_set_and_get(self, db):
        db.set_global_default("key1", "value1")
        assert db.get_global_default("key1") == "value1"

    def test_set_and_get_json(self, db):
        db.set_global_default("schedule", ["08:00", "20:00"])
        result = db.get_global_default("schedule")
        assert result == ["08:00", "20:00"]

    def test_get_nonexistent(self, db):
        assert db.get_global_default("nonexistent") is None

    def test_skip_if_exists(self, db):
        db.set_global_default("key1", "original")
        db.set_global_default("key1", "updated", skip_if_exists=True)
        assert db.get_global_default("key1") == "original"

    def test_skip_if_exists_allows_new(self, db):
        db.set_global_default("key1", "value", skip_if_exists=True)
        assert db.get_global_default("key1") == "value"

    def test_delete_global_default(self, db):
        db.set_global_default("key1", "value")
        db.delete_global_default("key1")
        assert db.get_global_default("key1") is None

    def test_list_global_defaults(self, db):
        db.set_global_default("a", 1)
        db.set_global_default("b", 2)
        result = db.list_global_defaults()
        assert result == {"a": 1, "b": 2}

    def test_get_admin_value_delegates(self, db):
        db.set_global_default("key1", "value1")
        assert db.get_admin_value("key1") == "value1"


class TestUserConfig:
    def test_save_and_load(self, db_with_user):
        db_with_user.save_user_config(1, "place", "Moscow")
        config = db_with_user.load_user_config(1)
        assert config["place"] == "Moscow"

    def test_load_empty_config(self, db_with_user):
        config = db_with_user.load_user_config(1)
        assert config == {}

    def test_delete_user_config_key(self, db_with_user):
        db_with_user.save_user_config(1, "place", "Moscow")
        db_with_user.delete_user_config_key(1, "place")
        config = db_with_user.load_user_config(1)
        assert "place" not in config

    def test_save_creates_user_if_missing(self, db):
        db.save_user_config(999, "place", "Berlin")
        assert db.user_exists(999) is True


class TestEffectiveValue:
    def test_user_override_takes_precedence(self, db):
        db.set_global_default("place", "Moscow")
        db.save_user_config(1, "place", "London")
        assert db.get_effective_value(1, "place") == "London"

    def test_falls_back_to_global(self, db):
        db.set_global_default("place", "Moscow")
        assert db.get_effective_value(1, "place") == "Moscow"

    def test_returns_none_when_no_value(self, db):
        assert db.get_effective_value(1, "place") is None


class TestSchedule:
    def test_load_schedule_default(self, db):
        result = db.load_schedule(1)
        assert result == []

    def test_save_and_load_schedule(self, db):
        db.save_schedule(1, ["08:00", "20:00"])
        result = db.load_schedule(1)
        assert result == ["08:00", "20:00"]


class TestCache:
    def test_compute_cache_hash_deterministic(self, db):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"image data")
            src = Path(f.name)
        try:
            db.ensure_user(1)
            db.save_base_image(1, src)
            h1 = db.compute_cache_hash(1, "test prompt")
            h2 = db.compute_cache_hash(1, "test prompt")
            assert h1 == h2
        finally:
            src.unlink(missing_ok=True)

    def test_compute_cache_hash_different_prompt(self, db):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"image data")
            src = Path(f.name)
        try:
            db.ensure_user(1)
            db.save_base_image(1, src)
            h1 = db.compute_cache_hash(1, "prompt A")
            h2 = db.compute_cache_hash(1, "prompt B")
            assert h1 != h2
        finally:
            src.unlink(missing_ok=True)

    def test_compute_cache_hash_raises_without_image(self, db):
        with pytest.raises(RuntimeError, match="No base image"):
            db.compute_cache_hash(999, "prompt")

    def test_check_cache_miss(self, db):
        assert db.check_cache(1, "nonexistent_hash") is None

    def test_check_cache_hit(self, db, tmp_data_dir):
        user_dir = tmp_data_dir / "users" / "1"
        user_dir.mkdir(parents=True, exist_ok=True)
        cache_file = user_dir / "abc123.jpg"
        cache_file.write_bytes(b"cached image")
        result = db.check_cache(1, "abc123")
        assert result == str(cache_file)

    def test_get_cache_path(self, db):
        path = db.get_cache_path(1, "hash123")
        assert str(path).endswith("hash123.jpg")