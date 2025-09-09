import asyncio
import logging
from pathlib import Path
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest

from dava.config import Config
from dava.generators.image_generator import ImageGenerator

logger = logging.getLogger(__name__)

class NanoBana(ImageGenerator):
    def __init__(self, config: Config):
        self.prompt = None
        self.config = config
        self.client = TelegramClient("user_session", config.api_id, config.api_hash)
        self.avatar_path = str((Path(config.image_dir) / "avatar.jpg").absolute())
        self.save_path = str((Path(config.image_dir) / "new_avatar.jpg").absolute())
        self._setup_handlers()

    async def generate_and_save_image(self, prompt: str) -> str:
        self.prompt = prompt
        await self._send_start_message()
        await self.client.start()
        try:
            await asyncio.wait_for(self.client.run_until_disconnected(), timeout=60.0 * 10)
        except asyncio.TimeoutError:
            await self.client.disconnect()
            raise Exception("Avatar not updated due to timeout")
        return str(self.save_path)

    async def _send_start_message(self):
        async with self.client:
            logger.info("sending /photo request")
            await asyncio.sleep(1)
            await self.client.send_message(self.config.nano_banana_chat_id, "/photo")

    def _setup_handlers(self):
        def check_generator_selector(event):
            text = "🍌 Gemini Images"
            return (event.message.reply_markup is not None and event.message.reply_markup.rows is not None and len(event.message.reply_markup.rows) > 0 and
                    len(event.message.reply_markup.rows[0].buttons) > 1 and text in event.message.reply_markup.rows[0].buttons[1].text
            )

        def check_prompt_response(event):
            text = "Write in the chat what you'd like to change on the image"
            ru = "Напишите в чат, что изменить на загруженном изображении"
            return text in event.message.text or ru in event.message.text

        def check_file_send(event):
            text = "Uncompressed image"
            ru = "Изображение без сжатия"
            return text in event.message.text or ru in event.message.text

        @self.client.on(events.NewMessage(chats=self.config.nano_banana_chat_id, func=check_generator_selector))
        async def process_message(event):
            logger.info("selecting nano banana")
            await asyncio.sleep(1)
            await self.client(GetBotCallbackAnswerRequest(event.message.peer_id, event.message.id, data = event.message.reply_markup.rows[0].buttons[1].data))
            logger.info("sending photo")
            await asyncio.sleep(1)
            await self.client.send_file(event.message.peer_id, file=self.avatar_path)

        @self.client.on(events.NewMessage(chats=self.config.nano_banana_chat_id, func=check_prompt_response))
        async def process_message(event):
            logger.info("sending prompt")
            await asyncio.sleep(1)
            await self.client.send_message(event.message.peer_id, self.prompt)

        @self.client.on(events.NewMessage(chats=self.config.nano_banana_chat_id, func=check_file_send))
        async def process_message(event):
            logger.info("downloading image")
            await asyncio.sleep(1)
            await event.message.download_media(file=self.save_path)
            logger.info("image successfully created!")
            self.client.disconnect()
