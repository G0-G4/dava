import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class AuthManager:
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._file = data_dir / "allowed_users.json"
        self._admins: set[int] = set()
        self._allowed: set[int] = set()
        self._load_admins()
        self._load_allowed()

    def _load_admins(self):
        env_value = os.getenv("admin_chat_ids", "")
        if env_value:
            for id_str in env_value.split(","):
                id_str = id_str.strip()
                if id_str:
                    self._admins.add(int(id_str))
        logger.info(f"Admin IDs: {self._admins}")

    def _load_allowed(self):
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text())
                self._allowed = set(data.get("allowed_user_ids", []))
            except (json.JSONDecodeError, KeyError):
                self._allowed = set()
        logger.info(f"Allowed user IDs: {self._allowed}")

    def _save(self):
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps({
            "allowed_user_ids": sorted(self._allowed)
        }, indent=2))

    def is_admin(self, user_id: int) -> bool:
        return user_id in self._admins

    def is_allowed(self, user_id: int) -> bool:
        return user_id in self._allowed or user_id in self._admins

    def grant(self, user_id: int):
        self._allowed.add(user_id)
        self._save()
        logger.info(f"Granted access to user {user_id}")

    def revoke(self, user_id: int):
        self._allowed.discard(user_id)
        self._save()
        logger.info(f"Revoked access from user {user_id}")

    def list_allowed(self) -> list[int]:
        return sorted(self._allowed | self._admins)