import asyncio
import base64
import json
import logging
from pathlib import Path

import aiohttp
import aiofiles

from dava.errors import RequestError

logger = logging.getLogger(__name__)

POLZA_BASE_URL = "https://polza.ai/api/v1"


class PolzaBase:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def _encode_image(self, image_path: str) -> str:
        path = Path(image_path)
        logger.debug(f"Reading and encoding image from {path}")
        with open(path, "rb") as f:
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

    async def _download_to_file(self, url: str, output_path: str) -> str:
        save_path = Path(output_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise RequestError(f"Download failed: {resp.status}")
                content = await resp.read()
                async with aiofiles.open(save_path, "wb") as f:
                    await f.write(content)
        logger.info(f"Downloaded to {save_path}")
        return str(save_path.absolute())