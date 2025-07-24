import logging

from telethon import TelegramClient
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.types import InputPhoto

from dava.avatar_generator import AvatarGenerator
from dava.config import Config
logger = logging.getLogger(__name__)


class AvatarUpdater:
    def __init__(self, avatar_generator: AvatarGenerator, config: Config):
        self.avatar_generator = avatar_generator
        self.client = TelegramClient("user_session", config.api_id, config.api_hash)

    async def async_update_avatar(self):
        async with self.client:
            img = await self.avatar_generator.save_image()
            logger.debug("deleting avatar")
            await self._delete_avatar()
            logger.debug("uploading new avatar")
            file = await self.client.upload_file(img)
            await self.client(UploadProfilePhotoRequest(file=file))
            logger.info("avatar UPDATED!")

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
