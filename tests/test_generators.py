from unittest.mock import MagicMock

import pytest

from dava.config import ImageGenerators, VideoGenerators
from dava.generators import get_image_generator, get_video_generator
from dava.generators.image_generator import ImageGenerator
from dava.generators.video_generator import VideoGenerator
from dava.generators.stable_diffusion_generator import StableDiffusionGenerator
from dava.generators.nano_banana_generator import NanoBananaGenerator
from dava.generators.veo_generator import VeoGenerator


class TestGetImageGenerator:
    def test_default_is_nano_banana_2(self):
        mock_config = MagicMock()
        result = get_image_generator(mock_config)
        assert isinstance(result, NanoBananaGenerator)

    def test_stable_diffusion(self):
        mock_config = MagicMock()
        result = get_image_generator(mock_config, image_generator=ImageGenerators.STABLE_DIFFUSION)
        assert isinstance(result, StableDiffusionGenerator)

    def test_nano_banana(self):
        mock_config = MagicMock()
        result = get_image_generator(mock_config, image_generator=ImageGenerators.NANO_BANANA)
        assert isinstance(result, NanoBananaGenerator)

    def test_nano_banana_2(self):
        mock_config = MagicMock()
        result = get_image_generator(mock_config, image_generator=ImageGenerators.NANO_BANANA_2)
        assert isinstance(result, NanoBananaGenerator)

    def test_style_string_conversion(self):
        mock_config = MagicMock()
        result = get_image_generator(
            mock_config,
            image_generator=ImageGenerators.STABLE_DIFFUSION,
            style="sai-photographic",
        )
        assert isinstance(result, StableDiffusionGenerator)

    def test_invalid_style_string(self):
        mock_config = MagicMock()
        result = get_image_generator(
            mock_config,
            image_generator=ImageGenerators.STABLE_DIFFUSION,
            style="invalid-style",
        )
        assert isinstance(result, StableDiffusionGenerator)

    def test_unknown_generator_defaults_to_nb2(self):
        mock_config = MagicMock()
        result = get_image_generator(mock_config, image_generator=None)
        assert isinstance(result, NanoBananaGenerator)


class TestGetVideoGenerator:
    def test_default_is_veo3_fast(self):
        mock_config = MagicMock()
        result = get_video_generator(mock_config)
        assert isinstance(result, VeoGenerator)
        assert result._model == "google/veo3_fast"

    def test_enum_param(self):
        mock_config = MagicMock()
        result = get_video_generator(mock_config, video_generator=VideoGenerators.VEO3_FAST)
        assert isinstance(result, VeoGenerator)
        assert result._model == "google/veo3_fast"

    def test_string_param(self):
        mock_config = MagicMock()
        result = get_video_generator(mock_config, video_generator="google/veo3_fast")
        assert isinstance(result, VeoGenerator)

    def test_none_defaults_to_veo3_fast(self):
        mock_config = MagicMock()
        result = get_video_generator(mock_config, video_generator=None)
        assert result._model == "google/veo3_fast"


class TestImageGeneratorABC:
    def test_cannot_instantiate(self):
        import pytest
        with pytest.raises(TypeError):
            ImageGenerator()

    def test_abstract_method_defined(self):
        assert hasattr(ImageGenerator, 'generate_and_save_image')
        import inspect
        assert inspect.iscoroutinefunction(ImageGenerator.generate_and_save_image)


class TestVideoGeneratorABC:
    def test_cannot_instantiate(self):
        import pytest
        with pytest.raises(TypeError):
            VideoGenerator()

    def test_abstract_method_defined(self):
        assert hasattr(VideoGenerator, 'generate_and_save_video')
        import inspect
        assert inspect.iscoroutinefunction(VideoGenerator.generate_and_save_video)
    def test_hermes(self):
        mock_config = MagicMock()
        result = get_image_generator(mock_config, image_generator=ImageGenerators.HERMES)
        from dava.generators.hermes_image_generator import HermesImageGenerator
        assert isinstance(result, HermesImageGenerator)

    def test_hermes_with_overrides(self):
        mock_config = MagicMock()
        result = get_image_generator(
            mock_config,
            image_generator=ImageGenerators.HERMES,
            hermes_auth_path="/tmp/fake-auth.json",
            hermes_xai_image_model="grok-imagine-image",
        )
        from dava.generators.hermes_image_generator import HermesImageGenerator
        assert isinstance(result, HermesImageGenerator)
        assert result._auth_path == "/tmp/fake-auth.json"
        assert result._model == "grok-imagine-image"

    def test_hermes_with_xai_auth_path(self):
        mock_config = MagicMock()
        result = get_image_generator(
            mock_config,
            image_generator=ImageGenerators.HERMES,
            xai_auth_path="/tmp/dava-xai.json",
        )
        from dava.generators.hermes_image_generator import HermesImageGenerator
        assert isinstance(result, HermesImageGenerator)
        assert result._auth_path == "/tmp/dava-xai.json"


class TestGetVideoGeneratorHermes:
    def test_hermes(self):
        mock_config = MagicMock()
        result = get_video_generator(mock_config, video_generator=VideoGenerators.HERMES)
        from dava.generators.hermes_video_generator import HermesVideoGenerator
        assert isinstance(result, HermesVideoGenerator)

    def test_hermes_string(self):
        mock_config = MagicMock()
        result = get_video_generator(mock_config, video_generator="hermes")
        from dava.generators.hermes_video_generator import HermesVideoGenerator
        assert isinstance(result, HermesVideoGenerator)

    def test_hermes_video_with_overrides(self):
        mock_config = MagicMock()
        result = get_video_generator(
            mock_config,
            video_generator=VideoGenerators.HERMES,
            hermes_auth_path="/tmp/fake.json",
            hermes_xai_video_model="grok-imagine-video-1.5-preview",
        )
        from dava.generators.hermes_video_generator import HermesVideoGenerator
        assert isinstance(result, HermesVideoGenerator)
        assert result._auth_path == "/tmp/fake.json"
        assert result._model == "grok-imagine-video-1.5-preview"

    def test_hermes_video_with_xai_auth_path(self):
        mock_config = MagicMock()
        result = get_video_generator(
            mock_config,
            video_generator=VideoGenerators.HERMES,
            xai_auth_path="/tmp/dava-xai-video.json",
        )
        from dava.generators.hermes_video_generator import HermesVideoGenerator
        assert isinstance(result, HermesVideoGenerator)
        assert result._auth_path == "/tmp/dava-xai-video.json"


# Basic smoke tests for the dedicated xAI auth manager (no network)
class TestXaiAuthManager:
    def test_mask_token_reexport(self):
        from dava.generators.xai_auth import mask_token as xai_mask
        assert xai_mask("abcdef1234567890") == "abcdef...7890"
        assert xai_mask("") == "<empty>"

    @pytest.mark.asyncio
    async def test_load_missing_returns_none(self, tmp_path):
        from dava.generators.xai_auth import load_xai_tokens
        p = tmp_path / "nope.json"
        assert await load_xai_tokens(str(p)) is None

    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(self, tmp_path):
        from dava.generators.xai_auth import save_xai_tokens, load_xai_tokens
        target = tmp_path / "xai.json"
        tokens = {
            "access_token": "acc_123456",
            "refresh_token": "ref_abcdef",
            "expires_in": 21600,
        }
        path = await save_xai_tokens(str(target), tokens)
        loaded = await load_xai_tokens(str(path))
        assert loaded is not None
        assert loaded["access_token"] == "acc_123456"
        assert "last_refresh" in loaded
        # file should be 0600 (best effort on the test fs)
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600 or mode == 0o666  # some test envs ignore umask
