import json
import logging

from dava.config import Config, ImageGenerators
from dava.errors import RequestError
from dava.generators.polza_base import PolzaBase
from dava.generators.image_generator import ImageGenerator

logger = logging.getLogger(__name__)

NANO_BANANA_MODELS = {
    "nano-banana": "google/gemini-2.5-flash-image",
    "nano-banana-2": "google/gemini-3.1-flash-image-preview",
}


class NanoBananaGenerator(PolzaBase, ImageGenerator):
    def __init__(self, config: Config, polza_model: str | None = None, image_generator: ImageGenerators | None = None):
        PolzaBase.__init__(self, api_key=config.polza_api_key)
        self._config = config
        self._polza_model = polza_model
        self._image_generator = image_generator

    def _get_model(self) -> str:
        model = self._polza_model
        if model:
            if model in NANO_BANANA_MODELS:
                return NANO_BANANA_MODELS[model]
            return model
        generator = self._image_generator
        if generator and generator.value in NANO_BANANA_MODELS:
            return NANO_BANANA_MODELS[generator.value]
        return NANO_BANANA_MODELS["nano-banana"]

    async def generate_and_save_image(self, prompt: str, input_image_path: str, output_path: str) -> str:
        image_b64 = self._encode_image(input_image_path)

        payload = {
            "model": self._get_model(),
            "input": {
                "prompt": prompt,
                "images": [{"type": "base64", "data": image_b64}],
                "aspect_ratio": "1:1",
                "output_format": "jpeg",
            },
        }

        response = await self._create_media(payload)
        logger.info(f"Polza create response: {json.dumps(response, indent=2)}")
        media_id = response.get("id")
        if not media_id:
            raise RequestError(f"No media ID in response: {response}") from None

        status = response.get("status")
        if status == "completed":
            image_url = self._extract_url(response.get("data"))
        elif status in ("pending", "processing"):
            image_url = await self._poll_media(media_id)
        else:
            raise RequestError(f"Unexpected initial status: {status}, response: {response}") from None

        return await self._download_to_file(image_url, output_path)