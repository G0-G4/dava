import json
import logging

from dava.config import Config
from dava.errors import RequestError
from dava.generators.polza_base import PolzaBase
from dava.generators.video_generator import VideoGenerator

logger = logging.getLogger(__name__)

DEFAULT_VIDEO_MODEL = "google/veo3_fast"


class VeoGenerator(PolzaBase, VideoGenerator):
    def __init__(self, config: Config, model: str | None = None):
        PolzaBase.__init__(self, api_key=config.polza_api_key)
        self._model = model or DEFAULT_VIDEO_MODEL

    async def generate_and_save_video(
        self, prompt: str, reference_image_path: str, output_path: str
    ) -> str:
        image_b64 = self._encode_image(reference_image_path)

        payload = {
            "model": self._model,
            "input": {
                "prompt": prompt,
                "aspect_ratio": "9:16",
                "images": [{"type": "base64", "data": image_b64}],
                "generationType": "REFERENCE_2_VIDEO",
                "enableTranslation": "true",
            },
            "async": True,
        }

        response = await self._create_media(payload)
        logger.info(f"Veo create response: {json.dumps(response, indent=2)}")
        media_id = response.get("id")
        if not media_id:
            raise RequestError(f"No media ID in response: {response}") from None

        video_url = await self._poll_media(media_id, timeout=600, interval=10)

        return await self._download_to_file(video_url, output_path)