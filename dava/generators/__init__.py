from dava.config import Config, ImageGenerators
from dava.generators.nano_banana_generator import NanoBananaGenerator
from dava.generators.stable_diffusion_generator import StableDiffusionGenerator


def get_image_generator(config: Config):
    return {
        ImageGenerators.STABLE_DIFFUSION: StableDiffusionGenerator(config),
        ImageGenerators.NANO_BANANA: NanoBananaGenerator(config),
        ImageGenerators.NANO_BANANA_2: NanoBananaGenerator(config),
    }.get(config.image_generator, StableDiffusionGenerator(config))