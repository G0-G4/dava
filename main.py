import asyncio
import logging
import os
from pathlib import Path

from telethon import TelegramClient

from dava.avatar_updater import AvatarUpdater
from dava.config import Config
from dava.db import Database
from dava.logs import setup_logging
from dava.raw_handlers import RawHandlers
from dava.service import DavaService
from dava.transport import DavaTelethonTransport, parse_proxy_url
from dava.tuican_app import create_app
from dava.weather_descriptor import WeatherDescriptor

if __name__ == "__main__":
    setup_logging()

    async def main():
        config = Config()
        data_dir = Path(config.data_dir)
        db = Database(data_dir / "bot.db", data_dir, admin_ids=set(config.admin_chat_ids))
        weather_descriptor = WeatherDescriptor()
        updater = AvatarUpdater(config, db)
        service = DavaService(config, db, updater, weather_descriptor)

        # Create Telethon client (same session name as before for compatibility)
        client = TelegramClient("bot_session", config.api_id, config.api_hash)
        if proxy_url := os.getenv("PROXY"):
            client.set_proxy(parse_proxy_url(proxy_url))
        updater.client = client

        # Raw handlers for photos and business connections
        RawHandlers(client, service)

        # Create TUIcan app with custom transport wrapping the client
        app = create_app(config, service, client)

        # Restore schedules
        service.restore_all_schedules()

        # Start TUIcan (which starts the client and runs until disconnected)
        app.run()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Shutting down gracefully...")
