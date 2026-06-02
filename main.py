import asyncio
import logging
from pathlib import Path

from dava.auth import AuthManager
from dava.avatar_updater import AvatarUpdater
from dava.bot_controller import BotController
from dava.config import Config
from dava.logs import setup_logging
from dava.user_store import UserStore
from dava.weather_descriptor import WeatherDescriptor, logger

if __name__ == "__main__":
    setup_logging()

    async def main():
        config = Config()
        data_dir = Path(config.data_dir)
        auth = AuthManager(data_dir)
        users = UserStore(data_dir)
        weather_descriptor = WeatherDescriptor(config)
        updater = AvatarUpdater(config, users)
        bot = BotController(updater, weather_descriptor, config, auth, users)
        updater.client = bot.client
        bot.restore_all_schedules()
        await bot.start()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")