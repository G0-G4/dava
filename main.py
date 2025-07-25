import asyncio

from dava.avatar_generator import AvatarGenerator
from dava.avatar_updater import AvatarUpdater
from dava.bot_controller import BotController
from dava.config import Config
from dava.logs import setup_logging
from dava.weather_descriptor import WeatherDescriptor, logger

if __name__ == "__main__":
    setup_logging()

    async def main():
        config = Config()
        weather_descriptor = WeatherDescriptor(config)
        generator = AvatarGenerator(weather_descriptor, config)
        updater = AvatarUpdater(generator, config)

        bot = BotController(updater, weather_descriptor, generator, config)
        # Start bot
        await bot.start()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")