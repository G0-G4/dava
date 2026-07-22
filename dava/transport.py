import logging
from urllib.parse import urlparse

from telethon import TelegramClient, events
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault
from tuican.transports.telethon_transport import TelethonTransport

logger = logging.getLogger(__name__)


class DavaTelethonTransport(TelethonTransport):
    """Custom Telethon transport that wraps an existing TelegramClient.

    Designed for use inside an already-running asyncio event loop
    (e.g. ``async def main()`` + ``asyncio.run()``).  The caller is
    responsible for connecting the client *before* invoking ``start()``.
    """

    def __init__(self, client: TelegramClient, token: str, api_id: int, api_hash: str):
        super().__init__(token, api_id, api_hash)
        self._client = client

    def start(self, application_core) -> None:
        """Register TUIcan handlers.  Client must already be connected."""
        self._application_core = application_core
        self._client.add_event_handler(
            self._on_new_message, events.NewMessage
        )
        self._client.add_event_handler(
            self._on_callback_query, events.CallbackQuery
        )
        logger.debug("TelethonTransport handlers registered")

    def run(self) -> None:
        """Blocking is not supported inside an async context.

        Use ``await transport.run_async()`` instead.
        """
        raise RuntimeError(
            "DavaTelethonTransport.run() cannot be used inside an async context. "
            "Use 'await transport.run_async()' instead."
        )

    async def run_async(self) -> None:
        """Async-safe equivalent of ``run_until_disconnected()``."""
        await self._client.disconnected


async def setup_bot_commands(client: TelegramClient) -> None:
    """Set the bot command menu. Must be called after client is connected."""
    commands = [
        ("start", "Start bot"),
        ("help", "Show help message"),
        ("settings", "Interactive settings menu (recommended)"),
        ("update", "Force avatar update now"),
        ("upload", "Upload base image"),
        ("upload_reference", "Upload scene reference image (for stable background)"),
        ("generate_reference", "Generate scene reference (uses neutral clear conditions for stable bg)"),
        ("clear_reference", "Clear current scene reference"),
        ("video_mode", "Set video generation mode"),
        ("schedule", "Show your update schedule"),
        ("add_time", "Add new update time (HH:MM)"),
        ("delete_time", "Delete update time (HH:MM)"),
        ("connection", "Show your business connection"),
        ("weather", "Show current weather"),
        ("set_variable", "Set config variable"),
        ("set_action", "Set video action"),
        ("delete_action", "Delete video action"),
    ]
    admin_commands = [
        ("logs", "Show recent logs"),
        ("grant", "Grant access to user"),
        ("revoke", "Revoke access from user"),
        ("list_users", "List all users with access"),
        ("set_global_variable", "Set global config variable"),
    ]
    try:
        await client(
            SetBotCommandsRequest(
                scope=BotCommandScopeDefault(),
                lang_code="en",
                commands=[BotCommand(*cmd) for cmd in commands + admin_commands],
            )
        )
        logger.info("Bot command menu set up successfully")
    except Exception:
        logger.warning("Failed to set bot commands", exc_info=True)


def parse_proxy_url(proxy_url: str) -> dict:
    parsed = urlparse(proxy_url)
    proxy_type = parsed.scheme.lower()
    if proxy_type not in ("socks5", "socks4", "http"):
        raise ValueError(f"Unsupported proxy type: {proxy_type}")
    proxy_dict = {
        "proxy_type": proxy_type,
        "addr": parsed.hostname,
        "port": parsed.port,
    }
    if parsed.username:
        proxy_dict["username"] = parsed.username
    if parsed.password:
        proxy_dict["password"] = parsed.password
    return proxy_dict
