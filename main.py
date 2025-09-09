import asyncio

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
        updater = AvatarUpdater(config)
        bot = BotController(updater, weather_descriptor, config)
        # Start bot
        await bot.start()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")