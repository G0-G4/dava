from unittest.mock import MagicMock

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