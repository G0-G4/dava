import logging

import aiohttp
from telethon import TelegramClient
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from telethon.tl.types import InputUser

from dava.config import Config
from dava.generators import get_image_generator

logger = logging.getLogger(__name__)


class AvatarUpdater:
    def __init__(self, config: Config):
        self.config = config
        self.client: TelegramClient | None = None

    async def async_update_avatar(self, prompt: str):
        connection = self.config.load_connection()
        if not connection:
            raise RuntimeError(
                "No business connection found. "
                "Connect the bot to your account via Settings > Chat Automation in Telegram."
            )

        if not self.client:
            raise RuntimeError("Bot client not initialized")

        connection_id = connection["connection_id"]
        user_id = connection["user_id"]

        img = await get_image_generator(self.config).generate_and_save_image(prompt)

        logger.debug("deleting old avatar via Bot API")
        await self._delete_avatar(connection_id)
        logger.debug("uploading new avatar")
        file = await self.client.upload_file(img)
        await self.client(UploadProfilePhotoRequest(
            bot=InputUser(user_id=user_id, access_hash=0),
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