import asyncio

from telethon import TelegramClient
from dava.avatar_updater import AvatarUpdater
from dava.bot_controller import BotController
from dava.config import Config
from dava.generators.nano_banana_avatar_generator import NanoBana
from dava.generators.stable_diffusion_generator import StableDiffusionGenerator
from dava.logs import setup_logging
from dava.weather_descriptor import WeatherDescriptor, logger

if __name__ == "__main__":
    setup_logging()

    async def main():
        config = Config()
        weather_descriptor = WeatherDescriptor(config)
        #generator = StableDiffusionGenerator(weather_descriptor, config)
        generator = NanoBana(config)
        updater = AvatarUpdater(generator, config)
        bot = BotController(updater, weather_descriptor, config)
        # Start bot
        await bot.start()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")