import base64
import json
import logging
from pathlib import Path

import aiohttp

from dava.errors import RequestError
from dava.generators.hermes_auth import mask_token
from dava.generators.xai_auth import get_xai_access_token, HERMES_XAI_USER_AGENT
from dava.generators.image_generator import ImageGenerator

logger = logging.getLogger(__name__)

XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_IMAGE_MODEL = "grok-imagine-image-quality"


class HermesImageGenerator(ImageGenerator):
    """
    Image generator that calls the *real* xAI Grok Imagine endpoints
    using a dedicated OAuth token obtained for dava
    (via scripts/init_xai_auth.py or equivalent device-code flow).

    Independent of any Hermes Agent token on the same machine.
    """

    def __init__(self, config=None, **kwargs):
        self._config = config
        # Prefer the new dedicated xai_auth_path. Fall back to hermes_auth_path
        # only for transition (the old key is no longer the runtime source).
        self._auth_path = (
            kwargs.get("xai_auth_path")
            or kwargs.get("hermes_auth_path")
        )
        self._model = kwargs.get("hermes_xai_image_model") or DEFAULT_IMAGE_MODEL

        if not self._auth_path and config:
            if hasattr(config, "get"):
                self._auth_path = config.get("xai_auth_path") or config.get("hermes_auth_path")
                if not self._model or self._model == DEFAULT_IMAGE_MODEL:
                    self._model = config.get("hermes_xai_image_model") or DEFAULT_IMAGE_MODEL
            else:
                self._auth_path = (
                    getattr(config, "xai_auth_path", None)
                    or getattr(config, "hermes_auth_path", None)
                    or self._auth_path
                )
                if not self._model or self._model == DEFAULT_IMAGE_MODEL:
                    self._model = getattr(config, "hermes_xai_image_model", None) or DEFAULT_IMAGE_MODEL

    async def _get_token(self) -> str:
        token = await get_xai_access_token(self._auth_path)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Using xAI token masked={mask_token(token)} (len={len(token)})")
        return token

    async def generate_and_save_image(self, prompt: str, input_image_path: str, output_path: str) -> str:
        token = await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": HERMES_XAI_USER_AGENT,
        }

        # Always send the input (base or scene reference) image for identity / scene consistency.
        # xAI uses /v1/images/edits for reference-guided generation.
        image_b64 = self._encode_image(input_image_path)
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

        logger.info(f"Using real xAI Grok Imagine ({self._model}) via xAI OAuth for image generation (reference-based)")

        data = await self._post_with_refresh_retry(
            f"{XAI_BASE_URL}/images/edits",
            payload=payload,
            initial_headers=headers,
            timeout=300,
        )

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

    async def _post_with_refresh_retry(
        self,
        url: str,
        *,
        payload: dict,
        initial_headers: dict,
        timeout: int = 300,
    ) -> dict:
        """
        POST with one automatic refresh + retry when the access token
        is rejected (401 or 403 "bad-credentials"/"unauthenticated").
        """
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, json=payload, headers=initial_headers) as resp:
                text = await resp.text()
                if resp.status == 200:
                    return json.loads(text) if text else {}

                body_lower = text.lower()
                is_token_invalid = (
                    resp.status in (401, 403) or
                    "bad-credentials" in body_lower or
                    "unauthenticated" in body_lower or
                    "could not be validated" in body_lower or
                    "invalid token" in body_lower
                )
                if not is_token_invalid:
                    raise RequestError(f"xAI request failed: {resp.status} - {text}")

        # Token rejected → force refresh and retry once
        logger.warning(f"xAI auth error {resp.status} (token invalid), forcing refresh + retry")
        new_token = await get_xai_access_token(self._auth_path, force_refresh=True)
        headers2 = {**initial_headers, "Authorization": f"Bearer {new_token}"}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.post(url, json=payload, headers=headers2) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise RequestError(f"xAI request failed after refresh: {resp.status} - {text}")
                return json.loads(text) if text else {}

    def _encode_image(self, image_path: str) -> str:
        path = Path(image_path)
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
