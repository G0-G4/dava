import asyncio
import logging
from pathlib import Path

import aiohttp
from telethon import TelegramClient
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from telethon.tl.types import InputUser

from dava.config import Config, ImageGenerators, Style, VideoGenerators
from dava.db import Database
from dava.generators import get_image_generator, get_video_generator

logger = logging.getLogger(__name__)

MAX_VIDEO_DURATION = 10


class AvatarUpdater:
    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.client: TelegramClient | None = None

    async def async_update_avatar(
        self,
        prompt: str,
        user_id: int,
        image_generator: ImageGenerators | None = None,
        polza_model: str | None = None,
        style: Style | str | None = None,
        image_cfg_scale: float | None = None,
        image_url: str | None = None,
    ):
        connection = self.db.load_connection(user_id)
        if not connection:
            raise RuntimeError(
                "No business connection found. "
                "Connect the bot to your account via Settings > Chat Automation in Telegram."
            )

        if not self.client:
            raise RuntimeError("Bot client not initialized")

        if not self.db.has_base_image(user_id):
            raise RuntimeError(
                "No base image found. Use /upload to send your base image first."
            )

        connection_id = connection["connection_id"]
        tg_user_id = connection["user_id"]

        base_image_path = self.db.get_base_image_path(user_id)
        if not base_image_path:
            raise RuntimeError("Base image path not found in database.")

        cache_hash = self.db.compute_cache_hash(user_id, prompt, mode="image")
        cached = self.db.check_cache(user_id, cache_hash, mode="image")
        if cached:
            logger.info(f"User {user_id}: Cache hit, using cached image {cached}")
            img_path = cached
        else:
            logger.info(f"User {user_id}: Cache miss, generating new image")
            output_path = str(self.db.get_cache_path(user_id, cache_hash, mode="image"))
            generator = get_image_generator(
                self.config,
                image_generator=image_generator,
                polza_model=polza_model,
                style=style,
                image_cfg_scale=image_cfg_scale,
                image_url=image_url,
            )
            img_path = await generator.generate_and_save_image(
                prompt, base_image_path, output_path
            )

        logger.debug("deleting old avatar via Bot API")
        await self._delete_avatar(connection_id)
        logger.debug("uploading new avatar")
        file = await self.client.upload_file(img_path)
        await self.client(UploadProfilePhotoRequest(
            bot=InputUser(user_id=tg_user_id, access_hash=0),
            file=file,
        ))

    async def async_update_video_avatar(
        self,
        prompt: str,
        user_id: int,
        video_generator: VideoGenerators | str | None = None,
    ):
        connection = self.db.load_connection(user_id)
        if not connection:
            raise RuntimeError(
                "No business connection found. "
                "Connect the bot to your account via Settings > Chat Automation in Telegram."
            )

        if not self.client:
            raise RuntimeError("Bot client not initialized")

        if not self.db.has_base_image(user_id):
            raise RuntimeError(
                "No base image found. Use /upload to send your base image first."
            )

        connection_id = connection["connection_id"]
        tg_user_id = connection["user_id"]

        base_image_path = self.db.get_base_image_path(user_id)
        if not base_image_path:
            raise RuntimeError("Base image path not found in database.")

        cache_hash = self.db.compute_cache_hash(user_id, prompt, mode="video")
        cached = self.db.check_cache(user_id, cache_hash, mode="video")
        if cached:
            logger.info(f"User {user_id}: Cache hit, using cached video {cached}")
            video_path = cached
        else:
            logger.info(f"User {user_id}: Cache miss, generating new video")
            output_path = str(self.db.get_cache_path(user_id, cache_hash, mode="video"))
            generator = get_video_generator(self.config, video_generator=video_generator)
            video_path = await generator.generate_and_save_video(
                prompt, base_image_path, output_path
            )

        video_path = await self._prepare_video(video_path)

        static_path = await self._extract_first_frame(video_path)

        logger.debug("deleting old avatar via Bot API")
        await self._delete_avatar(connection_id)
        logger.debug("uploading new video avatar")
        video_file = await self.client.upload_file(video_path)
        static_file = await self.client.upload_file(static_path)
        await self.client(UploadProfilePhotoRequest(
            bot=InputUser(user_id=tg_user_id, access_hash=0),
            file=static_file,
            video=video_file,
        ))

    async def _prepare_video(self, video_path: str) -> str:
        result = await self._truncate_video(video_path)
        result = await self._crop_to_square(result)
        return result

    async def _truncate_video(self, video_path: str) -> str:
        input_path = Path(video_path)
        truncated_path = str(input_path.with_stem(input_path.stem + "_5s"))
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-t", str(MAX_VIDEO_DURATION),
            "-vf", "format=yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-an",
            "-movflags", "+faststart",
            truncated_path,
        ]
        logger.info(f"Truncating video to {MAX_VIDEO_DURATION}s: {video_path} -> {truncated_path}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            logger.warning(f"ffmpeg truncate failed (code {process.returncode}), using original video: {stderr.decode()[-500:]}")
            return video_path
        if not Path(truncated_path).exists():
            logger.warning("ffmpeg truncate produced no output, using original video")
            return video_path
        duration = await self._get_video_duration(truncated_path)
        if duration is not None and duration <= MAX_VIDEO_DURATION:
            logger.info(f"Video truncated to {duration:.1f}s")
            return truncated_path
        logger.warning(f"Truncated video still longer than {MAX_VIDEO_DURATION}s ({duration:.1f}s), using original")
        return truncated_path

    async def _crop_to_square(self, video_path: str) -> str:
        input_path = Path(video_path)
        cropped_path = str(input_path.with_stem(input_path.stem + "_1x1"))
        crop_filter = "crop=min(iw\\,ih):min(iw\\,ih):(iw-min(iw\\,ih))/2:(ih-min(iw\\,ih))/2,format=yuv420p"
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", crop_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-an",
            "-movflags", "+faststart",
            cropped_path,
        ]
        logger.info(f"Cropping video to 1:1 square: {video_path} -> {cropped_path}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            logger.warning(f"ffmpeg crop failed (code {process.returncode}), falling back to original video: {stderr.decode()[-500:]}")
            return video_path
        if not Path(cropped_path).exists():
            logger.warning("ffmpeg crop produced no output, falling back to original video")
            return video_path
        logger.info(f"Successfully cropped video to 1:1: {cropped_path}")
        return cropped_path

    async def _extract_first_frame(self, video_path: str) -> str:
        output_path = str(Path(video_path).with_suffix(".jpg"))
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            output_path,
        ]
        logger.info(f"Extracting first frame: {video_path} -> {output_path}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            logger.warning(f"ffmpeg frame extraction failed (code {process.returncode}): {stderr.decode()[-500:]}")
            raise RuntimeError(f"Failed to extract first frame from video: ffmpeg code {process.returncode}")
        if not Path(output_path).exists():
            raise RuntimeError(f"ffmpeg did not produce frame output: {output_path}")
        logger.info(f"Extracted first frame to {output_path}")
        return output_path

    async def _get_video_duration(self, video_path: str) -> float | None:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            video_path,
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0:
                return float(stdout.decode().strip())
        except Exception:
            pass
        return None

    async def _delete_avatar(self, connection_id: str):
        url = f"https://api.telegram.org/bot{self.config.bot_token}/removeBusinessAccountProfilePhoto"
        payload = {
            "business_connection_id": connection_id,
            "is_public": False,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning(f"Failed to delete old profile photo: {resp.status} {text}")