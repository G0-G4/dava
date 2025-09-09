from dava.config import Config, ImageGenerators
from dava.generators.nano_banana_avatar_generator import NanoBana
from dava.generators.stable_diffusion_generator import StableDiffusionGenerator


def get_image_generator(config: Config):
    return {
        ImageGenerators.STABLE_DIFFUSION : StableDiffusionGenerator(config),
        ImageGenerators.NANO_BANANA: NanoBana(config),
    }.get(config.image_generator, StableDiffusionGenerator(config))