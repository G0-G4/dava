import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str | Path, data_dir: str | Path, admin_ids: set[int] | None = None, auto_create: bool = False):
        self._db_path = Path(db_path)
        self._data_dir = Path(data_dir)
        self._admin_ids: set[int] = admin_ids or set()
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        if auto_create:
            self._create_tables()
        self._data_dir.mkdir(parents=True, exist_ok=True)
        (self._data_dir / "users").mkdir(parents=True, exist_ok=True)

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                is_allowed BOOLEAN NOT NULL DEFAULT 0,
                connection_id TEXT,
                connection_user_id INTEGER,
                edit_profile_photo BOOLEAN,
                base_image_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_config (
                user_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (user_id, key),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS global_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        self._conn.commit()

    # -- Users --

    def ensure_user(self, user_id: int):
        self._conn.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
        )
        self._conn.commit()

    def is_admin(self, user_id: int) -> bool:
        return user_id in self._admin_ids

    def is_allowed(self, user_id: int) -> bool:
        row = self._conn.execute(
            "SELECT is_allowed FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row and row["is_allowed"]:
            return True
        return self.is_admin(user_id)

    def grant(self, user_id: int):
        self.ensure_user(user_id)
        self._conn.execute(
            "UPDATE users SET is_allowed = 1 WHERE user_id = ?", (user_id,)
        )
        self._conn.commit()
        logger.info(f"Granted access to user {user_id}")

    def revoke(self, user_id: int):
        self._conn.execute(
            "UPDATE users SET is_allowed = 0 WHERE user_id = ?", (user_id,)
        )
        self._conn.commit()
        logger.info(f"Revoked access from user {user_id}")

    def list_allowed(self) -> list[int]:
        rows = self._conn.execute(
            "SELECT user_id FROM users WHERE is_allowed = 1"
        ).fetchall()
        allowed = {row["user_id"] for row in rows}
        return sorted(allowed | self._admin_ids)

    def user_exists(self, user_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row is not None

    def list_users(self) -> list[int]:
        rows = self._conn.execute("SELECT user_id FROM users").fetchall()
        return sorted(row["user_id"] for row in rows)

    # -- Connections --

    def save_connection(self, user_id: int, connection_id: str, tg_user_id: int, rights: dict | None = None):
        self.ensure_user(user_id)
        edit_photo = False
        if rights:
            edit_photo = rights.get("edit_profile_photo", False)
        self._conn.execute(
            """UPDATE users SET connection_id = ?, connection_user_id = ?, edit_profile_photo = ?
               WHERE user_id = ?""",
            (connection_id, tg_user_id, edit_photo, user_id),
        )
        self._conn.commit()
        logger.info(f"Saved connection for user {user_id}")

    def load_connection(self, user_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT connection_id, connection_user_id, edit_profile_photo FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row or row["connection_id"] is None:
            return None
        result: dict[str, Any] = {
            "connection_id": row["connection_id"],
            "user_id": row["connection_user_id"],
        }
        if row["edit_profile_photo"] is not None:
            result["rights"] = {"edit_profile_photo": bool(row["edit_profile_photo"])}
        return result

    # -- Base image --

    def save_base_image(self, user_id: int, source_path: Path) -> str:
        import shutil
        dest_dir = self._data_dir / "users" / str(user_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "avatar.jpg"
        shutil.copy2(source_path, dest)
        self._conn.execute(
            "UPDATE users SET base_image_path = ? WHERE user_id = ?",
            (str(dest), user_id),
        )
        self._conn.commit()
        logger.info(f"Saved base image for user {user_id}")
        return str(dest)

    async def save_base_image_bytes(self, user_id: int, data: bytes) -> str:
        dest_dir = self._data_dir / "users" / str(user_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "avatar.jpg"
        dest.write_bytes(data)
        self._conn.execute(
            "UPDATE users SET base_image_path = ? WHERE user_id = ?",
            (str(dest), user_id),
        )
        self._conn.commit()
        logger.info(f"Saved base image for user {user_id}")
        return str(dest)

    def has_base_image(self, user_id: int) -> bool:
        row = self._conn.execute(
            "SELECT base_image_path FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row or not row["base_image_path"]:
            return False
        return Path(row["base_image_path"]).exists()

    def get_base_image_path(self, user_id: int) -> str | None:
        row = self._conn.execute(
            "SELECT base_image_path FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row or not row["base_image_path"]:
            fallback = self._data_dir / "users" / str(user_id) / "avatar.jpg"
            if fallback.exists():
                return str(fallback)
            return None
        return row["base_image_path"]

# -- Global config --

    def get_global_default(self, key: str):
        row = self._conn.execute(
            "SELECT value FROM global_config WHERE key = ?", (key,)
        ).fetchone()
        if row:
            return json.loads(row["value"])
        return None

    def set_global_default(self, key: str, value: Any, skip_if_exists: bool = False):
        if skip_if_exists:
            existing = self._conn.execute(
                "SELECT 1 FROM global_config WHERE key = ?", (key,)
            ).fetchone()
            if existing:
                return
        self._conn.execute(
            """INSERT INTO global_config (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, json.dumps(value)),
        )
        self._conn.commit()

    def delete_global_default(self, key: str):
        self._conn.execute(
            "DELETE FROM global_config WHERE key = ?", (key,)
        )
        self._conn.commit()

    def list_global_defaults(self) -> dict:
        rows = self._conn.execute("SELECT key, value FROM global_config").fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}

    def get_admin_value(self, key: str):
        return self.get_global_default(key)

    # -- User config --

    def load_user_config(self, user_id: int) -> dict:
        rows = self._conn.execute(
            "SELECT key, value FROM user_config WHERE user_id = ?", (user_id,)
        ).fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}

    def save_user_config(self, user_id: int, key: str, value: Any):
        self.ensure_user(user_id)
        self._conn.execute(
            """INSERT INTO user_config (user_id, key, value) VALUES (?, ?, ?)
               ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value""",
            (user_id, key, json.dumps(value)),
        )
        self._conn.commit()

    def delete_user_config_key(self, user_id: int, key: str):
        self._conn.execute(
            "DELETE FROM user_config WHERE user_id = ? AND key = ?", (user_id, key)
        )
        self._conn.commit()

    def get_effective_value(self, user_id: int, key: str):
        row = self._conn.execute(
            "SELECT value FROM user_config WHERE user_id = ? AND key = ?",
            (user_id, key),
        ).fetchone()
        if row:
            return json.loads(row["value"])
        return self.get_global_default(key)

    # -- Schedule convenience --

    def load_schedule(self, user_id: int) -> list:
        value = self.get_effective_value(user_id, "schedule")
        if value is None:
            return []
        return value

    def save_schedule(self, user_id: int, times: list):
        self.save_user_config(user_id, "schedule", times)

    # -- Cache --

    def compute_cache_hash(self, user_id: int, prompt: str, mode: str = "image") -> str:
        base_image_path = self.get_base_image_path(user_id)
        if not base_image_path:
            raise RuntimeError(f"No base image found for user {user_id}")
        image_bytes = Path(base_image_path).read_bytes()
        digest = hashlib.sha256(image_bytes + prompt.encode() + mode.encode()).hexdigest()
        return digest

    def get_cache_path(self, user_id: int, cache_hash: str, mode: str = "image") -> Path:
        user_dir = self._data_dir / "users" / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        ext = "mp4" if mode == "video" else "jpg"
        return user_dir / f"{cache_hash}.{ext}"

    def check_cache(self, user_id: int, cache_hash: str, mode: str = "image") -> str | None:
        path = self.get_cache_path(user_id, cache_hash, mode=mode)
        if path.exists():
            logger.info(f"Cache hit for user {user_id}: {cache_hash} ({mode})")
            return str(path)
        return None