from dava.config import Config, ImageGenerators, Style, VideoGenerators
from dava.generators.nano_banana_generator import NanoBananaGenerator
from dava.generators.stable_diffusion_generator import StableDiffusionGenerator
from dava.generators.veo_generator import VeoGenerator
from dava.generators.hermes_image_generator import HermesImageGenerator
from dava.generators.hermes_video_generator import HermesVideoGenerator
from dava.generators.video_generator import VideoGenerator


def get_image_generator(
    config: Config,
    image_generator: ImageGenerators | None = None,
    polza_model: str | None = None,
    style: Style | str | None = None,
    image_cfg_scale: float | None = None,
    image_url: str | None = None,
    hermes_auth_path: str | None = None,
    hermes_xai_image_model: str | None = None,
    xai_auth_path: str | None = None,
):
    if image_generator is None:
        image_generator = ImageGenerators.NANO_BANANA_2

    if isinstance(style, str):
        try:
            style = Style(style)
        except ValueError:
            style = None

    # Build hermes / xai config overrides (passed down from admin values)
    hermes_overrides = {}
    if hermes_auth_path:
        hermes_overrides["hermes_auth_path"] = hermes_auth_path
    if xai_auth_path:
        hermes_overrides["xai_auth_path"] = xai_auth_path
    if hermes_xai_image_model:
        hermes_overrides["hermes_xai_image_model"] = hermes_xai_image_model

    generator_map = {
        ImageGenerators.STABLE_DIFFUSION: StableDiffusionGenerator(
            config,
            image_cfg_scale=image_cfg_scale,
            style=style,
            image_url=image_url,
        ),
        ImageGenerators.NANO_BANANA: NanoBananaGenerator(
            config,
            polza_model=polza_model,
            image_generator=image_generator,
        ),
        ImageGenerators.NANO_BANANA_2: NanoBananaGenerator(
            config,
            polza_model=polza_model,
            image_generator=image_generator,
        ),
        ImageGenerators.HERMES: HermesImageGenerator(config, **hermes_overrides),
    }
    return generator_map.get(image_generator, StableDiffusionGenerator(
        config,
        image_cfg_scale=image_cfg_scale,
        style=style,
        image_url=image_url,
    ))


def get_video_generator(
    config: Config,
    video_generator: VideoGenerators | str | None = None,
    hermes_auth_path: str | None = None,
    hermes_xai_video_model: str | None = None,
    xai_auth_path: str | None = None,
) -> VideoGenerator:
    if video_generator is None:
        video_generator = VideoGenerators.VEO3_FAST
    if isinstance(video_generator, VideoGenerators):
        video_generator = video_generator.value

    if str(video_generator).lower() == "hermes":
        overrides = {}
        if hermes_auth_path:
            overrides["hermes_auth_path"] = hermes_auth_path
        if xai_auth_path:
            overrides["xai_auth_path"] = xai_auth_path
        if hermes_xai_video_model:
            overrides["hermes_xai_video_model"] = hermes_xai_video_model
        return HermesVideoGenerator(config, **overrides)

    # default to Veo
    return VeoGenerator(config, model=video_generator)
