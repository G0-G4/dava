"""Custom Telethon backend that uses Markdown parse mode."""

from telethon.client.telegramclient import TelegramClient
from tuican.backends.telethon_backend import TelethonBackend
from tuican.keyboard_button import KeyboardButton
from tuican.update import TuicanUpdate, UpdateKind


class DavaTelethonBackend(TelethonBackend):
    """Telethon backend that sends messages with Markdown formatting.

    The original dava bot used ``parse_mode="markdown"`` for all messages.
    TUIcan's default ``TelethonBackend`` hardcodes HTML mode and escapes
    text, which breaks Markdown syntax (``**bold**``, ``\`\`\`code\`\`\``).
    """

    def __init__(self, client: TelegramClient) -> None:
        super().__init__(client)

    async def send_keyboard_message(
        self,
        update: TuicanUpdate,
        text: str,
        keyboard_markup,
        parse_mode: str = "markdown",
    ) -> None:
        from telethon import Button
        from telethon.errors import MessageNotModifiedError, RPCError

        buttons = [
            [
                Button.inline(
                    button.text,
                    data=button.callback_data.encode(),
                )
                for button in row
                if button.callback_data is not None
            ]
            for row in keyboard_markup
        ]

        try:
            if update.kind == UpdateKind.CALLBACK:
                await self._client.edit_message(
                    update.chat_id,
                    update.message_id,
                    text=text,
                    buttons=buttons,
                    parse_mode=parse_mode,
                )
            else:
                await self._client.send_message(
                    entity=update.chat_id,
                    message=text,
                    buttons=buttons,
                    parse_mode=parse_mode,
                )
        except MessageNotModifiedError:
            pass
        except RPCError as exc:
            if "not modified" not in str(exc).lower():
                raise

    async def send_plain_message(
        self,
        update: TuicanUpdate,
        text: str,
    ) -> None:
        await self._client.send_message(
            update.chat_id,
            message=text,
            parse_mode="markdown",
        )
