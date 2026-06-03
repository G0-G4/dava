import json
import logging
import os
from enum import Enum
from dotenv import load_dotenv
from typing import get_type_hints

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

DEFAULT_VIDEO_PROMPT_TEXT = "Animated portrait of a person centered in frame, {action}, {detailed_description}, {lighting_description}, {place}"

EXTREME_WEATHER_CODES = frozenset({
    55, 57, 65, 66, 67,
    71, 73, 75, 77,
    82, 86,
    95, 96, 99,
})

DEFAULT_VIDEO_ACTIONS = {
    "weather": {
        "55": "thick drizzle falling steadily, rain streaks across the frame",
        "57": "intense freezing drizzle, ice forming on surfaces, shivering",
        "65": "torrential rain pouring in sheets, rapid splashing in puddles",
        "66": "freezing rain coating surfaces with ice, ice crackling",
        "67": "heavy freezing rain, ice accumulating, dramatic ice formations",
        "71": "gentle snowfall, snowflakes drifting softly in the air",
        "73": "moderate snowfall, snowflakes swirling in the wind",
        "75": "heavy snowfall with large flakes swirling in the wind, blizzard-like",
        "77": "snow grains scattering in the wind, icy particles dancing",
        "82": "violent rain showers, water splashing intensely, dramatic downpour",
        "86": "snow blowing sideways in gusty wind, wintry squall",
        "95": "dramatic lightning flash illuminating the scene, thunder rumble, wind howling",
        "96": "thunderstorm with hail stones bouncing off surfaces",
        "99": "intense thunderstorm with large hail, violent wind gusts, dramatic lightning",
    },
    "holidays": {
        "New Year's Day": "fireworks exploding in colorful bursts, confetti drifting down, festive lights twinkling",
        "Christmas Day": "twinkling Christmas lights, gentle snow falling, warm candlelight flickering",
        "Orthodox Christmas Day": "candle flame flickering softly, golden church bells, snow drifting gently",
        "Defender of the Fatherland Day": "military bands marching, flags waving in the wind",
        "International Women's Day": "flowers gently swaying, soft petals falling, warm spring light",
        "Spring and Labour Day": "cherry blossoms fluttering in a gentle breeze, bright sunshine",
        "Victory Day": "fireworks bursting over a city skyline, flags waving solemnly",
        "Russia Day": "flag waving proudly, fireworks lighting up the sky",
        "Unity Day": "warm candlelight glowing, autumn leaves swirling gently",
        "friday the 13th": "eerie fog rolling across the frame, candle flame flickering, shadows creeping along walls",
    },
}

DEFAULTS = {
    "video_actions": DEFAULT_VIDEO_ACTIONS,
    "video_prompt_text": DEFAULT_VIDEO_PROMPT_TEXT,
    "extreme_weather_codes": sorted(EXTREME_WEATHER_CODES),
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

    def migrate_env_to_db(self, db):
        for key in ALL_CONFIGURABLE_KEYS:
            raw = os.getenv(key)
            if raw is not None:
                try:
                    value = convert_value(key, raw)
                    db.set_global_default(key, value, skip_if_exists=True)
                    logger.info(f"Migrated .env key '{key}' to global_config")
                except Exception as e:
                    logger.warning(f"Failed to migrate .env key '{key}': {e}")

    def migrate_defaults_to_db(self, db):
        for key, value in DEFAULTS.items():
            db.set_global_default(key, value, skip_if_exists=True)
            logger.info(f"Seeded default for '{key}' to global_config")