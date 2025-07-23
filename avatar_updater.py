from telethon import TelegramClient
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.types import InputPhoto

from avatar_generator import AvatarGenerator
from config import API_HASH, API_ID, COOKIES, IMAGE_DIR
from weather_descriptor import WeatherDescriptor

class AvatarUpdater:

    def __init__(self, avatar_generator: AvatarGenerator):
        self.avatar_generator = avatar_generator
        self.client = TelegramClient("anon", API_ID, API_HASH)

    def update(self):
        img = self.avatar_generator.save_image()
        with self.client:
            self.client.loop.run_until_complete(self._update_avatar(img))

    async def _update_avatar(self, img):
        await self._delete_avatar()
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

if __name__ == "__main__":
    a = AvatarUpdater(AvatarGenerator(COOKIES, IMAGE_DIR, WeatherDescriptor()))
    a.update()