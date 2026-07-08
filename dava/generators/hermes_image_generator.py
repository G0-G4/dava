import base64
import json
import logging
from pathlib import Path

import aiohttp

from dava.errors import RequestError
from dava.generators.hermes_auth import get_hermes_xai_access_token, mask_token
from dava.generators.image_generator import ImageGenerator

logger = logging.getLogger(__name__)

XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_IMAGE_MODEL = "grok-imagine-image-quality"


class HermesImageGenerator(ImageGenerator):
    """
    Image generator that calls the *real* xAI Grok Imagine endpoints
    (https://api.x.ai/v1/images/generations and /v1/images/edits)
    using the OAuth token that Hermes obtained for the user
    (via `hermes model` / xai-oauth).

    This gives native Grok models (no FAL proxy) while reusing the
    login the user already performed in Hermes.
    """

    def __init__(self, config=None, **kwargs):
        self._config = config
        self._auth_path = kwargs.get("hermes_auth_path")
        self._model = kwargs.get("hermes_xai_image_model") or DEFAULT_IMAGE_MODEL

        if not self._auth_path and config:
            # Fallback to reading from the passed config object
            if hasattr(config, "get"):
                self._auth_path = config.get("hermes_auth_path")
                if not self._model or self._model == DEFAULT_IMAGE_MODEL:
                    self._model = config.get("hermes_xai_image_model") or DEFAULT_IMAGE_MODEL
            else:
                self._auth_path = getattr(config, "hermes_auth_path", None) or self._auth_path
                if not self._model or self._model == DEFAULT_IMAGE_MODEL:
                    self._model = getattr(config, "hermes_xai_image_model", None) or DEFAULT_IMAGE_MODEL

    def _get_token(self) -> str:
        token = get_hermes_xai_access_token(self._auth_path)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Using xAI token masked={mask_token(token)} (len={len(token)})")
        return token

    async def generate_and_save_image(self, prompt: str, base_image_path: str, output_path: str) -> str:
        token = self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "dava/1.0 (hermes-xai-grok)",
        }

        # Always send the base/reference image for identity consistency.
        # xAI uses /v1/images/edits for reference-guided generation.
        image_b64 = self._encode_image(base_image_path)
        image_payload = {
            "type": "image_url",
            "url": f"data:image/jpeg;base64,{image_b64}",
        }

        payload = {
            "model": self._model,
            "prompt": prompt,
            "image": image_payload,
            "aspect_ratio": "1:1",   # dava avatars are square
        }

        logger.info(f"Using real xAI Grok Imagine ({self._model}) via Hermes token for image generation (reference-based)")

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
            async with session.post(f"{XAI_BASE_URL}/images/edits", json=payload, headers=headers) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise RequestError(f"xAI image edit failed: {resp.status} - {text}")
                data = json.loads(text)

        # Response shape is OpenAI-compatible: {"data": [{"url": "..."} , ...]}
        image_url = None
        if isinstance(data, dict):
            items = data.get("data") or []
            if items and isinstance(items, list):
                first = items[0]
                image_url = first.get("url") if isinstance(first, dict) else None

        if not image_url:
            # Some responses may return base64 directly
            b64 = data.get("b64_json") if isinstance(data, dict) else None
            if not b64 and isinstance(data.get("data"), list) and data["data"]:
                b64 = data["data"][0].get("b64_json")
            if b64:
                save_path = Path(output_path)
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(base64.b64decode(b64))
                logger.info(f"xAI image (base64) saved to {save_path}")
                return str(save_path.absolute())

            raise RequestError(f"No image URL or base64 in xAI response: {data}")

        # Download the returned (temporary) URL
        save_path = Path(output_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as r:
                if r.status != 200:
                    raise RequestError(f"Failed to download xAI generated image: {r.status}")
                content = await r.read()
                save_path.write_bytes(content)

        logger.info(f"xAI image saved to {save_path}")
        return str(save_path.absolute())

    def _encode_image(self, image_path: str) -> str:
        path = Path(image_path)
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
