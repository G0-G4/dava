import asyncio
import logging
from pathlib import Path

from dava.avatar_updater import AvatarUpdater
from dava.bot_controller import BotController
from dava.config import Config
from dava.db import Database
from dava.logs import setup_logging
from dava.weather_descriptor import WeatherDescriptor, logger

if __name__ == "__main__":
    setup_logging()

    async def main():
        config = Config()
        data_dir = Path(config.data_dir)
        db = Database(data_dir / "bot.db", data_dir)
        weather_descriptor = WeatherDescriptor(config)
        updater = AvatarUpdater(config, db)
        bot = BotController(updater, weather_descriptor, config, db)
        updater.client = bot.client
        bot.restore_all_schedules()
        await bot.start()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")