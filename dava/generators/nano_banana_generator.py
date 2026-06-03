import asyncio
import base64
import json
import logging
from pathlib import Path

import aiohttp
import aiofiles

from dava.config import Config, ImageGenerators
from dava.errors import RequestError
from dava.generators.image_generator import ImageGenerator

logger = logging.getLogger(__name__)

POLZA_BASE_URL = "https://polza.ai/api/v1"

NANO_BANANA_MODELS = {
    "nano-banana": "google/gemini-2.5-flash-image",
    "nano-banana-2": "google/gemini-3.1-flash-image-preview",
}


class NanoBananaGenerator(ImageGenerator):
    def __init__(self, config: Config, polza_model: str | None = None, image_generator: ImageGenerators | None = None):
        self._config = config
        self._api_key = config.polza_api_key
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

    def _encode_image(self, base_image_path: str) -> str:
        image_path = Path(base_image_path)
        logger.debug(f"Reading and encoding image from {image_path}")
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()
            return f"data:image/jpeg;base64,{image_b64}"

    async def _create_media(self, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
            async with session.post(f"{POLZA_BASE_URL}/media", json=payload, headers=headers) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise RequestError(f"POST {POLZA_BASE_URL}/media failed: {resp.status} - {text}")
                return json.loads(text)

    def _extract_url(self, data) -> str:
        if isinstance(data, list):
            return data[0]["url"]
        if isinstance(data, dict):
            return data["url"]
        raise RequestError(f"Unexpected data format: {type(data)}")

    async def _poll_media(self, media_id: str, timeout: int = 300, interval: int = 5) -> str:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        elapsed = 0
        while elapsed < timeout:
            await asyncio.sleep(interval)
            elapsed += interval
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(
                    f"{POLZA_BASE_URL}/media/{media_id}",
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.warning(f"Media status check failed: {resp.status} {text}")
                        continue
                    data = await resp.json()
                    logger.info(f"Polza poll response: {json.dumps(data, indent=2)}")
                    status = data.get("status")

            logger.info(f"Polza media {media_id} status: {status}")

            if status == "completed":
                result_url = self._extract_url(data.get("data"))
                if not result_url:
                    raise RequestError(f"Completed media has no URL: {data}")
                return result_url

            if status == "failed":
                error = data.get("error", {})
                raise RequestError(f"Media generation failed: {error}")

        raise RequestError(f"Media generation timed out after {timeout}s")

    async def generate_and_save_image(self, prompt: str, base_image_path: str, output_path: str) -> str:
        image_b64 = self._encode_image(base_image_path)

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
            raise RequestError(f"No media ID in response: {response}")

        status = response.get("status")
        if status == "completed":
            image_url = self._extract_url(response.get("data"))
        elif status in ("pending", "processing"):
            image_url = await self._poll_media(media_id)
        else:
            raise RequestError(f"Unexpected initial status: {status}, response: {response}")

        save_path = Path(output_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    raise RequestError(f"Image download failed: {resp.status}")
                content = await resp.read()
                async with aiofiles.open(save_path, "wb") as f:
                    await f.write(content)

        logger.info(f"Image saved to {save_path}")
        return str(save_path.absolute())