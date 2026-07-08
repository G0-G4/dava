import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Optional

import aiohttp

from dava.errors import RequestError
from dava.generators.hermes_auth import get_hermes_xai_access_token, mask_token
from dava.generators.video_generator import VideoGenerator

logger = logging.getLogger(__name__)

XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_VIDEO_MODEL = "grok-imagine-video-1.5-preview"


class HermesVideoGenerator(VideoGenerator):
    """
    Video generator using real xAI Grok Imagine video endpoints
    with the OAuth token provisioned by Hermes.

    Uses image-to-video (reference image) + short duration.
    Final cropping/truncation to 1:1 3s is still done by AvatarUpdater.
    """

    def __init__(self, config=None, **kwargs):
        self._config = config
        self._auth_path = kwargs.get("hermes_auth_path")
        self._model = kwargs.get("hermes_xai_video_model") or DEFAULT_VIDEO_MODEL

        if not self._auth_path and config:
            if hasattr(config, "get"):
                self._auth_path = config.get("hermes_auth_path") or self._auth_path
                if not self._model or self._model == DEFAULT_VIDEO_MODEL:
                    self._model = config.get("hermes_xai_video_model") or DEFAULT_VIDEO_MODEL
            else:
                self._auth_path = getattr(config, "hermes_auth_path", None) or self._auth_path
                if not self._model or self._model == DEFAULT_VIDEO_MODEL:
                    self._model = getattr(config, "hermes_xai_video_model", None) or DEFAULT_VIDEO_MODEL

    def _get_token(self) -> str:
        token = get_hermes_xai_access_token(self._auth_path)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Using xAI token masked={mask_token(token)} (len={len(token)})")
        return token

    async def generate_and_save_video(
        self, prompt: str, reference_image_path: str, output_path: str
    ) -> str:
        token = self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "dava/1.0 (hermes-xai-grok)",
        }

        image_b64 = self._encode_image(reference_image_path)
        # For xAI video, just {"url": ...} like in Hermes plugin (no "type")
        image_payload = {
            "url": f"data:image/jpeg;base64,{image_b64}",
        }

        payload = {
            "model": self._model,
            "prompt": prompt,
            "image": image_payload,
            # duration / aspect handled by xAI or post-processed later
        }

        logger.info(f"Using real xAI Grok Imagine video ({self._model}) via Hermes token (image-to-video)")

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600)) as session:
            async with session.post(f"{XAI_BASE_URL}/videos/generations", json=payload, headers=headers) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise RequestError(f"xAI video create failed: {resp.status} - {text}")
                create_resp = json.loads(text)

        logger.debug(f"xAI video generations response: {create_resp}")

        # xAI returns {"request_id": "..."} for async jobs.
        # Immediate url is rare.
        video_id = None
        video_url = None

        if isinstance(create_resp, dict):
            video_id = create_resp.get("request_id") or create_resp.get("id")
            # Some responses may return the url directly
            data = create_resp.get("data") or create_resp
            if isinstance(data, list) and data:
                video_url = data[0].get("url") if isinstance(data[0], dict) else None
            elif isinstance(data, dict):
                video_url = data.get("url")

        if not video_url and video_id:
            logger.info(f"Starting poll for xAI video request_id={video_id}")
            video_url = await self._poll_video(video_id, token)

        if not video_url:
            raise RequestError(f"xAI did not return a video URL. Response: {create_resp}")

        # Download
        save_path = Path(output_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as r:
                if r.status != 200:
                    raise RequestError(f"Failed to download xAI video: {r.status}")
                content = await r.read()
                save_path.write_bytes(content)

        logger.info(f"xAI video saved to {save_path}")
        return str(save_path.absolute())

    async def _poll_video(self, video_id: str, token: str, timeout: int = 600, interval: int = 5) -> Optional[str]:
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "dava/1.0 (hermes-xai-grok)",
        }
        url = f"{XAI_BASE_URL}/videos/{video_id}"
        elapsed = 0

        async with aiohttp.ClientSession() as session:
            while elapsed < timeout:
                await asyncio.sleep(interval)
                elapsed += interval
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()

                status = (data.get("status") or "").lower() if isinstance(data, dict) else ""
                logger.info(f"xAI video {video_id} status: {status}")

                if status in ("completed", "succeeded", "success", "done"):
                    # xAI video done response structure (from Hermes plugin):
                    # often { "status": "done", "video": { "url": "...", "file_output": { "public_url": "..." } } }
                    # or direct "url", or under "data"
                    if isinstance(data, dict):
                        # direct
                        for k in ("url", "video_url"):
                            if data.get(k):
                                return data[k]
                        # video object
                        v = data.get("video")
                        if isinstance(v, dict):
                            for k in ("url", "video_url"):
                                if v.get(k):
                                    return v[k]
                            fo = v.get("file_output") or {}
                            if isinstance(fo, dict) and fo.get("public_url"):
                                return fo["public_url"]
                        # data
                        d = data.get("data") or {}
                        if isinstance(d, dict):
                            for k in ("url", "video_url"):
                                if d.get(k):
                                    return d[k]
                            vv = d.get("video") or {}
                            if isinstance(vv, dict):
                                for k in ("url", "video_url"):
                                    if vv.get(k):
                                        return vv[k]
                                fo = vv.get("file_output") or {}
                                if isinstance(fo, dict) and fo.get("public_url"):
                                    return fo["public_url"]
                    # done but no url found
                    logger.error(f"xAI video done but no URL found. Full response: {data}")
                    raise RequestError(f"xAI video generation completed (status={status}) but no URL found in response: {data}")

                if status in ("failed", "error", "expired", "cancelled"):
                    err = data.get("error") or data
                    raise RequestError(f"xAI video generation failed: {err}")

        raise RequestError(f"xAI video generation timed out after {timeout}s")

    def _encode_image(self, image_path: str) -> str:
        path = Path(image_path)
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
