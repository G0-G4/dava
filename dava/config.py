import logging
import os
from enum import Enum

from dotenv import load_dotenv

import json
from pathlib import Path
from typing import Dict, Any, get_type_hints

SCHEDULE_FILE = Path("../schedule.json")
CONNECTION_FILE = Path("connection.json")
logger = logging.getLogger(__name__)


class Style(Enum):
    SAI_PHOTOGRAPHIC = "sai-photographic"


class ImageGenerators(Enum):
    STABLE_DIFFUSION = "stable-diffusion"
    NANO_BANANA = "nano-banana"
    NANO_BANANA_2 = "nano-banana-2"


class Config:

    def __init__(self):
        load_dotenv()
        self._hidden = {"bot_token", "api_id", "api_hash", "image_dir", "previous_prompt_text", "polza_api_key"}

        self._config_store = {}
        self.properties = [name for name, value in vars(Config).items() if isinstance(value, property)]
        self.init_config()

    def init_config(self):
        for p in self.properties:
            getattr(self, p)

    def _get_converter(self, name):
        prop = getattr(type(self), name, None)
        if prop and isinstance(prop, property):
            try:
                hints = get_type_hints(prop.fget)
                return_type = hints.get("return")

                type_map = {
                    float: float,
                    int: int,
                    str: str,
                    dict: json.loads,
                    list: json.loads,
                    Style: lambda x: Style(x),
                    ImageGenerators: lambda x: ImageGenerators(x),
                }
                return type_map.get(return_type, str)
            except Exception:
                return str
        return str

    def __setitem__(self, key, value):
        if key in self.properties:
            self._config_store[key] = self._get_converter(key)(value)
            return
        self._config_store[key] = value

    def __delitem__(self, key):
        if key in self._config_store:
            del self._config_store[key]
            if key in self.properties:
                getattr(self, key)

    def _get_variable(self, name: str, required=True) -> Any:
        env_variable = os.getenv(name)
        if required and name not in self._config_store and env_variable is None:
            raise RuntimeError(f"required variable {name} not set")
        if name in self._config_store:
            return self._config_store[name]
        converted = self._get_converter(name)(env_variable) if env_variable is not None else None
        self._config_store[name] = converted
        return converted

    def all_variables(self) -> Dict[str, Any]:
        return {k: v for k, v in self._config_store.items() if k not in self._hidden}

    def save_schedule(self, times: list) -> None:
        SCHEDULE_FILE.write_text(json.dumps({"schedule": times}))

    def load_schedule(self) -> list:
        try:
            return json.loads(SCHEDULE_FILE.read_text()).get("schedule", [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def save_connection(self, connection_id: str, user_id: int, rights: dict | None = None) -> None:
        data = {"connection_id": connection_id, "user_id": user_id}
        if rights:
            data["rights"] = rights
        CONNECTION_FILE.write_text(json.dumps(data))

    def load_connection(self) -> dict | None:
        try:
            return json.loads(CONNECTION_FILE.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    @property
    def bot_token(self):
        return self._get_variable("bot_token")

    @property
    def prompt_text(self):
        return self._get_variable("prompt_text")

    @property
    def image_dir(self):
        return self._get_variable("image_dir")

    @property
    def cookies(self):
        return self._get_variable("cookies")

    @property
    def api_id(self):
        return self._get_variable("api_id")

    @property
    def api_hash(self):
        return self._get_variable("api_hash")

    @property
    def latitude(self) -> float:
        return self._get_variable("latitude")

    @property
    def longitude(self) -> float:
        return self._get_variable("longitude")

    @property
    def timezone(self):
        return self._get_variable("timezone")

    @property
    def place(self):
        return self._get_variable("place")

    @property
    def allowed_chat_id(self) -> int:
        return self._get_variable("allowed_chat_id")

    @property
    def previous_prompt_text(self):
        return self._get_variable("previous_prompt_text")

    @property
    def weather(self) -> dict:
        return self._get_variable("weather", required=False)

    @property
    def image_url(self):
        return self._get_variable("image_url", required=False)

    @property
    def image_cfg_scale(self) -> float:
        return self._get_variable("image_cfg_scale", required=True)

    @property
    def style(self) -> Style:
        return self._get_variable("style", required=False)

    @property
    def image_generator(self) -> ImageGenerators:
        return self._get_variable("image_generator", required=False)

    @property
    def holidays(self) -> dict:
        return self._get_variable("holidays", required=False)

    @property
    def polza_api_key(self):
        return self._get_variable("polza_api_key", required=False)

    @property
    def polza_model(self):
        return self._get_variable("polza_model", required=False)