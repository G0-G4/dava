import json
import logging
import os
from enum import Enum
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class Style(Enum):
    SAI_PHOTOGRAPHIC = "sai-photographic"


class ImageGenerators(Enum):
    STABLE_DIFFUSION = "stable-diffusion"
    NANO_BANANA = "nano-banana"
    NANO_BANANA_2 = "nano-banana-2"


class VideoGenerators(Enum):
    VEO3_FAST = "google/veo3_fast"


SYSTEM_KEYS = frozenset({
    "bot_token",
    "api_id",
    "api_hash",
    "polza_api_key",
    "cookies",
    "admin_chat_ids",
    "data_dir",
})

ADMIN_ONLY_KEYS = frozenset({
    "image_generator",
    "polza_model",
    "style",
    "image_cfg_scale",
    "image_url",
    "video_generator",
    "extreme_weather_codes",
})

USER_CONFIGURABLE_KEYS = frozenset({
    "prompt_text",
    "place",
    "latitude",
    "longitude",
    "timezone",
    "weather",
    "holidays",
    "video_mode",
    "video_actions",
    "video_prompt_text",
})

ALL_CONFIGURABLE_KEYS = ADMIN_ONLY_KEYS | USER_CONFIGURABLE_KEYS

_TYPE_MAP = {
    "image_generator": ImageGenerators,
    "polza_model": str,
    "style": Style,
    "image_cfg_scale": float,
    "image_url": str,
    "video_generator": VideoGenerators,
    "prompt_text": str,
    "place": str,
    "latitude": float,
    "longitude": float,
    "timezone": str,
    "weather": dict,
    "holidays": dict,
    "video_mode": str,
    "video_actions": dict,
    "video_prompt_text": str,
    "extreme_weather_codes": dict,
}


def convert_value(key: str, raw: str):
    type_fn = _TYPE_MAP.get(key, str)
    if type_fn is dict:
        return json.loads(raw)
    if type_fn is Style:
        return raw
    if type_fn is ImageGenerators:
        return raw
    return type_fn(raw)


class Config:

    def __init__(self):
        load_dotenv()
        self._hidden = {"bot_token", "api_id", "api_hash", "polza_api_key", "cookies"}

    def _get_variable(self, name: str, required=True) -> str | None:
        value = os.getenv(name)
        if required and value is None:
            raise RuntimeError(f"required variable {name} not set")
        return value

    @property
    def bot_token(self) -> str:
        return self._get_variable("bot_token")

    @property
    def api_id(self) -> str:
        return self._get_variable("api_id")

    @property
    def api_hash(self) -> str:
        return self._get_variable("api_hash")

    @property
    def polza_api_key(self) -> str:
        return self._get_variable("polza_api_key")

    @property
    def cookies(self) -> str:
        return self._get_variable("cookies")

    @property
    def admin_chat_ids(self) -> list[int]:
        raw = self._get_variable("admin_chat_ids", required=False) or ""
        return [int(x.strip()) for x in raw.split(",") if x.strip()]

    @property
    def data_dir(self) -> str:
        return self._get_variable("data_dir", required=False) or "data"

    def system_info(self) -> dict:
        return {
            k: v for k, v in {
                "bot_token": self.bot_token,
                "api_id": self.api_id,
                "api_hash": self.api_hash,
                "polza_api_key": self.polza_api_key,
                "cookies": self.cookies,
                "admin_chat_ids": self.admin_chat_ids,
                "data_dir": self.data_dir,
            }.items()
            if k not in self._hidden
        }