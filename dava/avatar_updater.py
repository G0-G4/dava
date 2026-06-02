import logging

import aiohttp
from telethon import TelegramClient
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from telethon.tl.types import InputUser

from dava.config import Config
from dava.generators import get_image_generator
from dava.user_store import UserStore

logger = logging.getLogger(__name__)


class AvatarUpdater:
    def __init__(self, config: Config, users: UserStore):
        self.config = config
        self.users = users
        self.client: TelegramClient | None = None

    async def async_update_avatar(self, prompt: str, user_id: int):
        connection = self.users.load_connection(user_id)
        if not connection:
            raise RuntimeError(
                "No business connection found. "
                "Connect the bot to your account via Settings > Chat Automation in Telegram."
            )

        if not self.client:
            raise RuntimeError("Bot client not initialized")

        if not self.users.has_base_image(user_id):
            raise RuntimeError(
                "No base image found. Use /upload to send your base image first."
            )

        connection_id = connection["connection_id"]
        tg_user_id = connection["user_id"]

        base_image_path = self.users.get_base_image_path(user_id)
        img = await get_image_generator(self.config).generate_and_save_image(prompt, str(base_image_path))

        logger.debug("deleting old avatar via Bot API")
        await self._delete_avatar(connection_id)
        logger.debug("uploading new avatar")
        file = await self.client.upload_file(img)
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