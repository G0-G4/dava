import logging

import aiohttp
from telethon import TelegramClient
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from telethon.tl.types import InputUser

from dava.config import Config, ImageGenerators, Style
from dava.db import Database
from dava.generators import get_image_generator

logger = logging.getLogger(__name__)


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

        cache_hash = self.db.compute_cache_hash(user_id, prompt)
        cached = self.db.check_cache(user_id, cache_hash)
        if cached:
            logger.info(f"User {user_id}: Cache hit, using cached image {cached}")
            img_path = cached
        else:
            logger.info(f"User {user_id}: Cache miss, generating new image")
            output_path = str(self.db.get_cache_path(user_id, cache_hash))
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