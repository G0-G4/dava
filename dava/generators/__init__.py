from dava.config import Config, ImageGenerators, Style
from dava.generators.nano_banana_generator import NanoBananaGenerator
from dava.generators.stable_diffusion_generator import StableDiffusionGenerator


def get_image_generator(
    config: Config,
    image_generator: ImageGenerators | None = None,
    polza_model: str | None = None,
    style: Style | str | None = None,
    image_cfg_scale: float | None = None,
    image_url: str | None = None,
):
    if image_generator is None:
        image_generator = ImageGenerators.NANO_BANANA_2

    if isinstance(style, str):
        try:
            style = Style(style)
        except ValueError:
            style = None

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
    }
    return generator_map.get(image_generator, StableDiffusionGenerator(
        config,
        image_cfg_scale=image_cfg_scale,
        style=style,
        image_url=image_url,
    ))