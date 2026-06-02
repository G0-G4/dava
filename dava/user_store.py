import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class UserStore:
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir / "users"

    def _user_dir(self, user_id: int) -> Path:
        return self._data_dir / str(user_id)

    def user_dir(self, user_id: int) -> Path:
        return self._user_dir(user_id)

    def user_exists(self, user_id: int) -> bool:
        return self._user_dir(user_id).exists()

    def _ensure_user_dir(self, user_id: int):
        self._user_dir(user_id).mkdir(parents=True, exist_ok=True)

    def save_connection(self, user_id: int, connection_id: str, tg_user_id: int, rights: dict | None = None):
        self._ensure_user_dir(user_id)
        data: dict[str, Any] = {"connection_id": connection_id, "user_id": tg_user_id}
        if rights:
            data["rights"] = rights
        (self._user_dir(user_id) / "connection.json").write_text(json.dumps(data))
        logger.info(f"Saved connection for user {user_id}")

    def load_connection(self, user_id: int) -> dict | None:
        path = self._user_dir(user_id) / "connection.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, KeyError):
            return None

    def save_base_image(self, user_id: int, source_path: Path) -> Path:
        self._ensure_user_dir(user_id)
        dest = self._user_dir(user_id) / "avatar.jpg"
        shutil.copy2(source_path, dest)
        logger.info(f"Saved base image for user {user_id} to {dest}")
        return dest

    async def save_base_image_bytes(self, user_id: int, data: bytes) -> Path:
        self._ensure_user_dir(user_id)
        dest = self._user_dir(user_id) / "avatar.jpg"
        dest.write_bytes(data)
        logger.info(f"Saved base image for user {user_id} to {dest}")
        return dest

    def has_base_image(self, user_id: int) -> bool:
        return (self._user_dir(user_id) / "avatar.jpg").exists()

    def get_base_image_path(self, user_id: int) -> Path:
        return self._user_dir(user_id) / "avatar.jpg"

    def get_output_path(self, user_id: int) -> Path:
        return self._user_dir(user_id) / "new_avatar.jpg"

    def load_user_config(self, user_id: int) -> dict:
        path = self._user_dir(user_id) / "config.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}

    def save_user_config(self, user_id: int, key: str, value: Any):
        self._ensure_user_dir(user_id)
        config = self.load_user_config(user_id)
        config[key] = value
        (self._user_dir(user_id) / "config.json").write_text(json.dumps(config, indent=2))

    def delete_user_config_key(self, user_id: int, key: str):
        config = self.load_user_config(user_id)
        config.pop(key, None)
        self._ensure_user_dir(user_id)
        (self._user_dir(user_id) / "config.json").write_text(json.dumps(config, indent=2))

    def load_schedule(self, user_id: int) -> list:
        config = self.load_user_config(user_id)
        return config.get("schedule", [])

    def save_schedule(self, user_id: int, times: list):
        config = self.load_user_config(user_id)
        config["schedule"] = times
        self._ensure_user_dir(user_id)
        (self._user_dir(user_id) / "config.json").write_text(json.dumps(config, indent=2))

    def list_users(self) -> list[int]:
        if not self._data_dir.exists():
            return []
        return sorted(int(d.name) for d in self._data_dir.iterdir() if d.is_dir() and d.name.isdigit())

    def get_effective_value(self, user_id: int, key: str, global_default=None):
        config = self.load_user_config(user_id)
        if key in config:
            return config[key]
        return global_default