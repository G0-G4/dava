import logging
import os

from dotenv import load_dotenv

import json
from pathlib import Path
from typing import Dict, Any

SCHEDULE_FILE = Path("../schedule.json")
logger = logging.getLogger(__name__)

class Config:

    def __init__(self):
        load_dotenv()
        self._hidden = {"bot_token", "api_id", "api_hash", "image_dir", "previous_prompt_text"}
        self._converters = {
            'latitude': float,
            'longitude': float,
            'allowed_chat_id': int,
            'weather': lambda x: json.loads(x),
        }

        self._config_store = {}
        self.properties = [name for name, value in vars(Config).items() if isinstance(value, property)]
        self.init_config()

    def init_config(self):
        # load all properties in memory
        for p in self.properties:
            getattr(self, p)

    def _get_converter(self, name):
        return self._converters.get(name, str)

    def __setitem__(self, key, value):
        if key in self.properties:
            self._config_store[key] = self._get_converter(key)(value)
            return
        self._config_store[key] = value


    def __delitem__(self, key):
        if key in self._config_store:
            del self._config_store[key]
            if key in self.properties:
                getattr(self, key) # load default from env

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
    def latitude(self):
        return self._get_variable("latitude")
    @property
    def longitude(self):
        return self._get_variable("longitude")
    @property
    def timezone(self):
        return self._get_variable("timezone")
    @property
    def place(self):
        return self._get_variable("place")

    @property
    def allowed_chat_id(self):
        return self._get_variable("allowed_chat_id")

    @property
    def previous_prompt_text(self):
        return self._get_variable("previous_prompt_text")

    @property
    def weather(self):
        return self._get_variable("weather", required=False)

    @property
    def image_url(self):
        return self._get_variable("image_url", required=False)

