import logging

from telethon import TelegramClient
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.types import InputPhoto

from dava.config import Config
from dava.generators import get_image_generator

logger = logging.getLogger(__name__)


class AvatarUpdater:
    def __init__(self, config: Config):
        self.config = config
        self.client = TelegramClient("user_session", config.api_id, config.api_hash)

    async def async_update_avatar(self, prompt: str):
        img = await get_image_generator(self.config).generate_and_save_image(prompt)
        async with self.client:
            logger.debug("deleting avatar")
            await self._delete_avatar()
            logger.debug("uploading new avatar")
            file = await self.client.upload_file(img)
            await self.client(UploadProfilePhotoRequest(file=file))

    async def _delete_avatar(self):
        photos = await self.client.get_profile_photos('me')
        if photos:
            await self.client(DeletePhotosRequest(
                id=[InputPhoto(
                    id=photos[0].id,
                    access_hash=photos[0].access_hash,
                    file_reference=photos[0].file_reference
                )]
            ))
