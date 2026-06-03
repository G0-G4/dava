import json
import os
from unittest.mock import patch, MagicMock

import pytest

from dava.config import Config, Style, ImageGenerators, VideoGenerators, convert_value, SYSTEM_KEYS, ADMIN_ONLY_KEYS, USER_CONFIGURABLE_KEYS


class TestConvertValue:
    def test_string_default(self):
        assert convert_value("prompt_text", "hello world") == "hello world"

    def test_float(self):
        assert convert_value("image_cfg_scale", "3.5") == 3.5

    def test_dict(self):
        raw = json.dumps({"key": "value"})
        assert convert_value("weather", raw) == {"key": "value"}

    def test_style_passthrough(self):
        assert convert_value("style", "sai-photographic") == "sai-photographic"

    def test_image_generator_passthrough(self):
        assert convert_value("image_generator", "nano-banana") == "nano-banana"

    def test_unknown_key_defaults_to_str(self):
        assert convert_value("unknown_key", "42") == "42"

    def test_convert_value_video_generator(self):
        result = convert_value("video_generator", "google/veo3_fast")
        assert result == VideoGenerators.VEO3_FAST

    def test_convert_value_video_mode(self):
        assert convert_value("video_mode", "auto") == "auto"

    def test_convert_value_video_actions(self):
        raw = json.dumps({"weather": {"95": "lightning"}})
        result = convert_value("video_actions", raw)
        assert result == {"weather": {"95": "lightning"}}

    def test_convert_value_extreme_weather_codes(self):
        raw = json.dumps([55, 65, 95])
        result = convert_value("extreme_weather_codes", raw)
        assert result == [55, 65, 95]


class TestEnums:
    def test_style_values(self):
        assert Style.SAI_PHOTOGRAPHIC.value == "sai-photographic"

    def test_image_generator_values(self):
        assert ImageGenerators.STABLE_DIFFUSION.value == "stable-diffusion"
        assert ImageGenerators.NANO_BANANA.value == "nano-banana"
        assert ImageGenerators.NANO_BANANA_2.value == "nano-banana-2"


class TestKeyCategories:
    def test_system_keys(self):
        assert "bot_token" in SYSTEM_KEYS
        assert "api_id" in SYSTEM_KEYS
        assert "api_hash" in SYSTEM_KEYS

    def test_admin_only_keys(self):
        assert "image_generator" in ADMIN_ONLY_KEYS
        assert "style" in ADMIN_ONLY_KEYS
        assert "extreme_weather_codes" in ADMIN_ONLY_KEYS

    def test_user_configurable_keys(self):
        assert "place" in USER_CONFIGURABLE_KEYS
        assert "prompt_text" in USER_CONFIGURABLE_KEYS
        assert "latitude" in USER_CONFIGURABLE_KEYS
        assert "video_mode" in USER_CONFIGURABLE_KEYS
        assert "video_actions" in USER_CONFIGURABLE_KEYS
        assert "video_prompt_text" in USER_CONFIGURABLE_KEYS

    def test_keys_disjoint(self):
        assert SYSTEM_KEYS.isdisjoint(USER_CONFIGURABLE_KEYS)
        assert SYSTEM_KEYS.isdisjoint(ADMIN_ONLY_KEYS)


class TestConfig:
    def test_init_loads_dotenv(self):
        with patch.dict(os.environ, {"bot_token": "x"}, clear=False):
            cfg = Config()
            assert cfg.bot_token == "x"

    def test_hidden_fields(self):
        with patch.dict(os.environ, {"bot_token": "secret"}, clear=False):
            cfg = Config()
            info = cfg.system_info()
            assert "bot_token" not in info
            assert "api_id" not in info
            assert "api_hash" not in info

    def test_admin_chat_ids_parsing(self):
        with patch.dict(os.environ, {"admin_chat_ids": "111,222,333"}, clear=False):
            cfg = Config()
            assert cfg.admin_chat_ids == [111, 222, 333]

    def test_admin_chat_ids_empty(self):
        with patch.dict(os.environ, {"admin_chat_ids": ""}, clear=False):
            cfg = Config()
            assert cfg.admin_chat_ids == []

    def test_admin_chat_ids_missing(self):
        with patch("dava.config.load_dotenv"):
            with patch.dict(os.environ, {}, clear=True):
                cfg = Config()
                assert cfg.admin_chat_ids == []

    def test_data_dir_default(self):
        with patch.dict(os.environ, {}, clear=False):
            cfg = Config()
            assert cfg.data_dir == "data"

    def test_data_dir_custom(self):
        with patch.dict(os.environ, {"data_dir": "/tmp/custom"}, clear=False):
            cfg = Config()
            assert cfg.data_dir == "/tmp/custom"