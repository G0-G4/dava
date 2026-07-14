import json
import logging
import os
import shlex
from datetime import datetime
from urllib.parse import urlparse

from telethon import TelegramClient, events
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault, KeyboardButtonCallback
from telethon.tl import types as tl_types
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from dava.avatar_updater import AvatarUpdater
from dava.config import (
    Config,
    USER_CONFIGURABLE_KEYS,
    ADMIN_ONLY_KEYS,
    ALL_CONFIGURABLE_KEYS,
    USER_SETTING_CATEGORIES,
    ADMIN_SETTING_CATEGORIES,
    ImageGenerators,
    VideoGenerators,
    convert_value,
)
from dava.db import Database
from dava.generators import get_image_generator
from dava.holidays import HolidayChecker
from dava.logs import get_recent_logs
from dava.weather_descriptor import WeatherDescriptor

logger = logging.getLogger(__name__)


def parse_proxy_url(proxy_url) -> dict:
    parsed = urlparse(proxy_url)

    proxy_type = parsed.scheme.lower()
    if proxy_type in ("socks5", "socks4", "http"):
        proxy_type = parsed.scheme.lower()
    else:
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


class BotController:
    def __init__(self, updater: AvatarUpdater, weather_descriptor: WeatherDescriptor, config: Config, db: Database):
        self.updater = updater
        self.weather_descriptor = weather_descriptor
        self.db = db
        self.client = TelegramClient("bot_session", config.api_id, config.api_hash)
        if PROXY := os.getenv("PROXY"):
            self.client.set_proxy(parse_proxy_url(PROXY))
        self.scheduler = AsyncIOScheduler()
        self._config = config
        self._pending_var: dict[int, str] = {}
        self._pending_time: set[int] = set()
        self._pending_upload: set[int] = set()
        self._pending_global_var: set[int] = set()
        self._pending_action: set[int] = set()
        self._pending_delete_action: set[int] = set()
        self._running_jobs: set[int] = set()
        self.holiday_checker = HolidayChecker()
        self._setup_handlers()

    async def start(self):
        await self.client.start(bot_token=self._config.bot_token)
        await self._setup_menu()
        await self.client.run_until_disconnected()

    async def _check_admin(self, event):
        if not self.db.is_admin(event.chat_id):
            await event.respond("⛔ This command is for admins only.")
            raise RuntimeError(f"Non-admin user {event.chat_id} tried admin command")

    async def _check_allowed(self, event):
        if not self.db.is_allowed(event.chat_id):
            await event.respond("⛔ Access not granted. Please contact the admin to get access.")
            raise RuntimeError(f"Unauthorized user {event.chat_id} tried to use bot")

    async def _send_long(self, event, title: str, value):
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False, indent=2)
        text = f"**{title}**:\n```\n{value}\n```"
        if len(text) <= 4096:
            await event.respond(text, parse_mode="markdown")
        else:
            chunks = [text[i:i + 4096] for i in range(0, len(text), 4096)]
            for chunk in chunks:
                await event.respond(chunk, parse_mode="markdown")

    def _get_effective_value(self, user_id: int, key: str):
        return self.db.get_effective_value(user_id, key)

    def _get_admin_value(self, key: str):
        return self.db.get_admin_value(key)

    # --- New helpers for hierarchical settings UI ---

    def _get_source_indicator(self, user_id: int, key: str, user_config: dict, global_config: dict) -> str:
        if key in user_config:
            return " (your override)"
        if key in global_config:
            return " (default)"
        return ""

    def _get_effective_display(self, user_id: int, key: str, truncate: int = 100) -> str:
        """Return a short human-friendly representation of the effective value."""
        val = self._get_effective_value(user_id, key)
        if val is None:
            return "(not set)"
        if isinstance(val, dict):
            try:
                n = len(val)
                # Special for video_actions
                if key == "video_actions":
                    w = len(val.get("weather", {}))
                    h = len(val.get("holidays", {}))
                    return f"dict ({w} weather + {h} holiday actions)"
                return f"dict ({n} keys)"
            except Exception:
                return "dict"
        if isinstance(val, (list, tuple)):
            return f"list ({len(val)} items)"
        s = str(val)
        if len(s) > truncate:
            return s[:truncate] + "…"
        return s

    def _is_complex_value(self, value) -> bool:
        """True for dicts, lists and long strings (the ones we want to offer 'View full' for)."""
        if value is None:
            return False
        if isinstance(value, (dict, list)):
            return True
        if isinstance(value, str) and len(value) > 60:
            return True
        return False

    def _should_offer_view_full(self, user_id: int, key: str) -> bool:
        """Whether to show a '👁 View full' button for this key (large JSON or prompt etc.)."""
        return self._is_complex_value(self._get_effective_value(user_id, key))

    async def _apply_video_action(self, user_id: int, action_type: str, key: str, action_text: str, event=None):
        """Shared logic to add/update a video action (used by command and menu flow)."""
        try:
            va = self._get_effective_value(user_id, "video_actions") or {}
            if isinstance(va, str):
                va = json.loads(va)
            if not isinstance(va, dict):
                va = {}
            va.setdefault(action_type, {})[key] = action_text
            self.db.save_user_config(user_id, "video_actions", va)
            msg = f"✅ Set {action_type}/{key} action."
            if event:
                await event.respond(msg)
        except Exception as e:
            if event:
                await event.respond(f"❌ Failed: {e}")

    async def _delete_video_action(self, user_id: int, action_type: str, key: str, event=None):
        """Shared logic to remove a video action (used by command and menu flow)."""
        try:
            va = self._get_effective_value(user_id, "video_actions") or {}
            if isinstance(va, str):
                va = json.loads(va)
            if isinstance(va, dict) and action_type in va and key in va[action_type]:
                del va[action_type][key]
                if not va.get(action_type):
                    va.pop(action_type, None)
                self.db.save_user_config(user_id, "video_actions", va)
                msg = f"✅ Removed {action_type}/{key}."
                if event:
                    await event.respond(msg)
            else:
                if event:
                    await event.respond("Action not found.")
        except Exception as e:
            if event:
                await event.respond(f"❌ Failed: {e}")

    def _build_settings_summary(self, user_id: int) -> str:
        """Build a readable grouped summary of current effective settings."""
        user_config = self.db.load_user_config(user_id)
        global_config = self.db.list_global_defaults()
        is_admin = user_id in self._config.admin_chat_ids

        lines = ["**Current settings** (effective values):"]

        for cat_name, keys in USER_SETTING_CATEGORIES.items():
            lines.append(f"\n{cat_name}")
            for k in keys:
                if k == "schedule":
                    continue
                ind = self._get_source_indicator(user_id, k, user_config, global_config)
                disp = self._get_effective_display(user_id, k)
                lines.append(f"• {k}: {disp}{ind}")

        # Show schedule separately (it's special)
        schedule = self.db.load_schedule(user_id)
        sched_disp = ", ".join(schedule) if schedule else "(none)"
        lines.append(f"\n📅 Schedule: {sched_disp}")

        # Custom keys (not in the known lists)
        customs = [
            k for k in user_config
            if k not in USER_CONFIGURABLE_KEYS and k not in ADMIN_ONLY_KEYS and k != "schedule"
        ]
        if customs:
            lines.append("\n🔸 Custom keys:")
            for k in sorted(customs):
                disp = self._get_effective_display(user_id, k)
                lines.append(f"• {k}: {disp}")

        if is_admin:
            lines.append("\n👑 You are admin — use Admin category for globals.")

        lines.append("\nTap a category below to view/edit.")
        return "\n".join(lines)

    def _build_main_category_buttons(self, is_admin: bool) -> list[list]:
        """Top-level category buttons (never a long vertical wall)."""
        buttons = []
        row = []
        for cat_name in USER_SETTING_CATEGORIES.keys():
            row.append(KeyboardButtonCallback(
                text=cat_name,
                data=f"cat:{cat_name}".encode(),
            ))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        # Schedule as its own prominent button
        buttons.append([KeyboardButtonCallback(text="📅 Schedule", data=b"cat:schedule")])

        if is_admin:
            buttons.append([KeyboardButtonCallback(text="👑 Admin / Globals", data=b"cat:globals")])

        # Quick actions row
        buttons.append([
            KeyboardButtonCallback(text="🔄 Refresh", data=b"cat:refresh"),
            KeyboardButtonCallback(text="❌ Close", data=b"cat:close"),
        ])
        return buttons

    def _build_category_view_text_and_buttons(self, user_id: int, cat: str):
        """Return (text, buttons) for a category submenu."""
        user_config = self.db.load_user_config(user_id)
        global_config = self.db.list_global_defaults()
        is_admin = user_id in self._config.admin_chat_ids

        text_lines = []
        buttons: list[list] = []

        if cat == "schedule":
            schedule = self.db.load_schedule(user_id)
            text_lines.append("**📅 Your update schedule** (UTC times)")
            if schedule:
                text_lines.append("Current: " + ", ".join(schedule))
            else:
                text_lines.append("No times set.")
            text_lines.append("\nUse the buttons or /add_time /delete_time.")
            for t in schedule:
                buttons.append([KeyboardButtonCallback(text=f"🗑 {t}", data=f"deletetime-{t}".encode())])
            buttons.append([KeyboardButtonCallback(text="➕ Add time (HH:MM)", data=b"addtime")])
            buttons.append([KeyboardButtonCallback(text="« Back", data=b"back:main")])
            return "\n".join(text_lines), buttons

        if cat == "globals" and is_admin:
            text_lines.append("**👑 Global defaults (affect all users)**")
            for cat_name, keys in ADMIN_SETTING_CATEGORIES.items():
                text_lines.append(f"\n{cat_name}")
                for k in keys:
                    disp = self._get_effective_display(user_id, k, truncate=80)
                    text_lines.append(f"• {k}: {disp}")
                    buttons.append([KeyboardButtonCallback(
                        text=f"✏️ {k}",
                        data=f"setglobalvar-{k}".encode(),
                    )])
                    if self._is_complex_value( global_config.get(k) ):
                        buttons.append([KeyboardButtonCallback(
                            text="👁 View full",
                            data=f"settings-admin-{k}".encode(),
                        )])
            buttons.append([KeyboardButtonCallback(text="« Back to main", data=b"back:main")])
            return "\n".join(text_lines), buttons

        # Regular user categories
        keys = USER_SETTING_CATEGORIES.get(cat, [])
        if not keys:
            text_lines.append(f"Category: {cat}")
        else:
            text_lines.append(f"**{cat}** — tap Edit to change")
            for k in keys:
                ind = self._get_source_indicator(user_id, k, user_config, global_config)
                disp = self._get_effective_display(user_id, k, truncate=80)
                text_lines.append(f"• {k}{ind}: {disp}")

                if k == "video_mode":
                    # Special direct toggles
                    buttons.append([
                        KeyboardButtonCallback(text="✅ auto", data=b"toggle:video_mode:auto"),
                        KeyboardButtonCallback(text="never", data=b"toggle:video_mode:never"),
                    ])
                else:
                    if k == "video_actions":
                        # Special handling + descriptive button added after the loop
                        pass
                    else:
                        edit_label = "✏️ Edit " + k
                        if k == "video_prompt_text":
                            edit_label = "✏️ Edit video prompt"
                        elif k == "prompt_text":
                            edit_label = "✏️ Edit prompt"
                        buttons.append([KeyboardButtonCallback(text=edit_label, data=f"edit:{k}".encode())])

                if self._should_offer_view_full(user_id, k) and k != "video_actions":
                    buttons.append([KeyboardButtonCallback(
                        text="👁 View full",
                        data=f"settings-user-{k}".encode(),
                    )])

            if cat == "🎥 Video":
                # Helpful note for complex actions
                va = self._get_effective_value(user_id, "video_actions") or {}
                if isinstance(va, str):
                    try:
                        import json as _j
                        va = _j.loads(va)
                    except Exception:
                        va = {}
                w = len(va.get("weather", {})) if isinstance(va, dict) else 0
                h = len(va.get("holidays", {})) if isinstance(va, dict) else 0
                text_lines.append(f"\nvideo_actions: {w} weather + {h} holiday entries")
                text_lines.append("Use buttons below or /set_action / /delete_action for quick edits.")
                buttons.append([
                    KeyboardButtonCallback(
                        text="✏️ Edit video_actions (full JSON)",
                        data=b"edit:video_actions",
                    ),
                    KeyboardButtonCallback(
                        text="👁 View full",
                        data=b"settings-user-video_actions",
                    ),
                ])
                buttons.append([KeyboardButtonCallback(
                    text="➕ Add action",
                    data=b"add_action",
                )])
                buttons.append([KeyboardButtonCallback(
                    text="🗑 Delete action",
                    data=b"delete_action",
                )])

        buttons.append([KeyboardButtonCallback(text="« Back", data=b"back:main")])
        return "\n".join(text_lines), buttons

    def _setup_handlers(self):
        @self.client.on(events.Raw(types=tl_types.UpdateBotBusinessConnect))
        async def business_connect_handler(update):
            connection = update.connection
            if not hasattr(connection, "connection_id") or not hasattr(connection, "user_id"):
                return

            rights = None
            if hasattr(connection, "rights") and connection.rights:
                rights = {
                    "edit_profile_photo": getattr(connection.rights, "edit_profile_photo", False),
                }

            user_id = connection.user_id
            self.db.save_connection(
                user_id=user_id,
                connection_id=connection.connection_id,
                tg_user_id=connection.user_id,
                rights=rights,
            )
            logger.info(f"Business connection established: {connection.connection_id} (user_id={user_id})")

            if self.db.is_allowed(user_id):
                has_photo_right = rights and rights.get("edit_profile_photo")
                status = "with" if has_photo_right else "without"
                await self.client.send_message(
                    user_id,
                    f"Business connection {status} profile photo editing rights.",
                )
            else:
                await self.client.send_message(
                    user_id,
                    "Your business connection has been received, but access has not been granted yet. "
                    "Please wait for the admin to approve your access.",
                )
                for admin_id in self.db.list_allowed():
                    if self.db.is_admin(admin_id):
                        await self.client.send_message(
                            admin_id,
                            f"New business connection request from user {user_id}. "
                            f"Use /grant {user_id} to allow access.",
                        )

        @self.client.on(events.CallbackQuery())
        async def callback_handler(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            if event.data.startswith(b"setvar-"):
                var_name = event.data.decode().split("-")[1]
                self._pending_var[user_id] = var_name
                await event.respond(f"Please send the new value for {var_name}")
            elif event.data.startswith(b"deletevar-"):
                var_name = event.data.decode().split("-")[1]
                self.db.delete_user_config_key(user_id, var_name)
                await event.respond(f"✅ {var_name} has been deleted")
            elif event.data.startswith(b"setglobalvar-"):
                var_name = event.data.decode().split("-")[1]
                self._pending_var[user_id] = var_name
                self._pending_global_var.add(user_id)
                await event.respond(f"Please send the new global value for {var_name}")
            elif event.data.startswith(b"deleteglobalvar-"):
                var_name = event.data.decode().split("-")[1]
                self.db.delete_global_default(var_name)
                await event.respond(f"✅ Global default {var_name} has been deleted")
            elif event.data.startswith(b"settings-admin-"):
                var_name = event.data.decode().split("-", 2)[2]
                global_config = self.db.list_global_defaults()
                val = global_config.get(var_name, "(not set)")
                await self._send_long(event, f"🔒 {var_name}", val)
            elif event.data.startswith(b"settings-user-"):
                var_name = event.data.decode().split("-", 2)[2]
                user_config = self.db.load_user_config(user_id)
                global_config = self.db.list_global_defaults()
                if var_name in user_config:
                    source = "your override"
                    val = user_config[var_name]
                elif var_name in global_config:
                    source = "default"
                    val = global_config[var_name]
                else:
                    source = ""
                    val = "(not set)"
                await self._send_long(event, f"👤 {var_name} ({source})", val)
            elif event.data.startswith(b"settings-custom-"):
                var_name = event.data.decode().split("-", 2)[2]
                user_config = self.db.load_user_config(user_id)
                val = user_config.get(var_name, "(not set)")
                await self._send_long(event, f"🔸 {var_name}", val)
            elif event.data.startswith(b"deletetime-"):
                time_str = event.data.decode().split("-")[1]
                schedule = self.db.load_schedule(user_id)
                if time_str in schedule:
                    schedule.remove(time_str)
                    self.db.save_schedule(user_id, schedule)
                    self._restart_scheduler(user_id)
                    await event.respond(f"⏰ Removed {time_str} from schedule")
                else:
                    await event.respond("⏰ Time not found in schedule")

            # --- New hierarchical menu navigation & actions (cat:*, edit:*, toggle:*, back:*) ---
            elif event.data.startswith(b"cat:"):
                payload = event.data.decode()[4:]  # after "cat:"
                try:
                    await event.edit("⏳ Loading...")
                except Exception:
                    pass
                if payload == "refresh":
                    is_admin = user_id in self._config.admin_chat_ids
                    summary = self._build_settings_summary(user_id)
                    buttons = self._build_main_category_buttons(is_admin)
                    try:
                        await event.edit(summary, parse_mode="markdown", buttons=buttons)
                    except Exception:
                        await event.respond(summary, parse_mode="markdown", buttons=buttons)
                    return
                if payload == "close":
                    try:
                        await event.edit("Settings closed. Use /settings to reopen.")
                    except Exception:
                        await event.respond("Settings closed.")
                    return
                text, btns = self._build_category_view_text_and_buttons(user_id, payload)
                try:
                    await event.edit(text, parse_mode="markdown", buttons=btns)
                except Exception:
                    await event.respond(text, parse_mode="markdown", buttons=btns)

            elif event.data.startswith(b"edit:"):
                key = event.data.decode().split(":", 1)[1]
                self._pending_var[user_id] = key
                # Try to guide in the same message if possible
                guide = f"✏️ Editing **{key}**\nCurrent effective value:\n```\n{self._get_effective_display(user_id, key, truncate=200)}\n```\n\nSend the new value now (multi-line OK for prompts). Type /cancel to abort."
                try:
                    await event.edit(guide, parse_mode="markdown")
                except Exception:
                    await event.respond(guide, parse_mode="markdown")

            elif event.data.startswith(b"toggle:"):
                # e.g. toggle:video_mode:auto
                _, key, val = event.data.decode().split(":", 2)
                if key == "video_mode" and val in ("auto", "never"):
                    self.db.save_user_config(user_id, key, val)
                    await event.respond(f"✅ video_mode set to {val}")
                    # Optionally refresh the parent menu (best-effort)
                    try:
                        is_admin = user_id in self._config.admin_chat_ids
                        summary = self._build_settings_summary(user_id)
                        buttons = self._build_main_category_buttons(is_admin)
                        # Can't easily know parent; just give quick re-open hint
                    except Exception:
                        pass
                else:
                    await event.respond("Unknown toggle.")

            elif event.data.startswith(b"back:main"):
                is_admin = user_id in self._config.admin_chat_ids
                summary = self._build_settings_summary(user_id)
                buttons = self._build_main_category_buttons(is_admin)
                try:
                    await event.edit(summary, parse_mode="markdown", buttons=buttons)
                except Exception:
                    await event.respond(summary, parse_mode="markdown", buttons=buttons)

            elif event.data.startswith(b"addtime"):
                self._pending_time.add(user_id)
                await event.respond("Please send the new time in HH:MM format (UTC)")

            elif event.data == b"add_action":
                self._pending_action.add(user_id)
                await event.respond(
                    "➕ Adding a video action.\n\n"
                    "Send in this format:\n"
                    "weather <code> <action text>\n"
                    "holiday \"name with spaces\" <action text>\n\n"
                    "Examples:\n"
                    "weather 95 lightning flash, user flinches\n"
                    "holiday \"New Year's Day\" fireworks, user cheers\n\n"
                    "You can also use the /set_action command.\n"
                    "Type /cancel to abort."
                )

            elif event.data == b"delete_action":
                self._pending_delete_action.add(user_id)
                await event.respond(
                    "🗑 Deleting a video action.\n\n"
                    "Send in this format:\n"
                    "weather <code>\n"
                    "holiday \"name with spaces\"\n\n"
                    "Example: weather 95\n\n"
                    "You can also use the /delete_action command.\n"
                    "Type /cancel to abort."
                )

        @self.client.on(events.NewMessage())
        async def handle_value_input(event):
            user_id = event.chat_id
            if not self.db.is_allowed(user_id):
                return
            try:
                if user_id in self._pending_var and not event.text.startswith("/"):
                    var_name = self._pending_var.pop(user_id)
                    new_value = event.text
                    is_global = user_id in self._pending_global_var
                    self._pending_global_var.discard(user_id)
                    if is_global:
                        converted = convert_value(var_name, new_value)
                        self.db.set_global_default(var_name, converted)
                        await event.respond(f"✅ Global default {var_name} set to {converted}")
                    else:
                        self.db.save_user_config(user_id, var_name, new_value)
                        await event.respond(f"✅ {var_name} set to {new_value}")
                elif user_id in self._pending_time and not event.text.startswith("/"):
                    self._pending_time.discard(user_id)
                    time_str = event.text.strip()
                    if not self._validate_time(time_str):
                        await event.respond("❌ Invalid time format. Use HH:MM")
                        return

                    schedule = self.db.load_schedule(user_id)
                    if time_str not in schedule:
                        schedule.append(time_str)
                        self.db.save_schedule(user_id, schedule)
                        self._restart_scheduler(user_id)
                        await event.respond(f"⏰ Added {time_str} to schedule")
                    else:
                        await event.respond("⏰ Time already exists in schedule")
                elif user_id in self._pending_action and not event.text.startswith("/"):
                    self._pending_action.discard(user_id)
                    text = event.text.strip()
                    try:
                        parts = shlex.split(text)
                    except ValueError:
                        parts = text.split()
                    if len(parts) < 3 or parts[0] not in ("weather", "holiday"):
                        await event.respond(
                            "❌ Invalid format.\n"
                            "Send e.g.:\n"
                            "weather 95 lightning flash, user flinches\n"
                            "holiday \"New Year's Day\" fireworks exploding\n\n"
                            "(Quote the key if it has spaces)"
                        )
                        return
                    action_type = parts[0]
                    key = parts[1]
                    action_text = " ".join(parts[2:])
                    await self._apply_video_action(user_id, action_type, key, action_text, event)
                elif user_id in self._pending_delete_action and not event.text.startswith("/"):
                    self._pending_delete_action.discard(user_id)
                    text = event.text.strip()
                    try:
                        parts = shlex.split(text)
                    except ValueError:
                        parts = text.split()
                    if len(parts) < 2 or parts[0] not in ("weather", "holiday"):
                        await event.respond(
                            "❌ Invalid format.\n"
                            "Send e.g.:\n"
                            "weather 95\n"
                            "holiday \"New Year's Day\"\n"
                        )
                        return
                    action_type = parts[0]
                    key = parts[1]
                    await self._delete_video_action(user_id, action_type, key, event)
                elif event.photo and user_id in self._pending_upload:
                    self._pending_upload.discard(user_id)
                    await self._handle_photo_upload(event, user_id)
            except Exception as e:
                await event.respond(f"❌ Error: {str(e)}")

        @self.client.on(events.NewMessage(pattern="/start"))
        async def start(event):
            await self._check_allowed(event)
            await self._send_help(event)

        @self.client.on(events.NewMessage(pattern="/help"))
        async def help(event):
            await self._check_allowed(event)
            await self._send_help(event)

        @self.client.on(events.NewMessage(pattern="/cancel"))
        async def cancel_pending(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            cleared = False
            if user_id in self._pending_var:
                self._pending_var.pop(user_id, None)
                cleared = True
            if user_id in self._pending_global_var:
                self._pending_global_var.discard(user_id)
                cleared = True
            if user_id in self._pending_time:
                self._pending_time.discard(user_id)
                cleared = True
            if user_id in self._pending_upload:
                self._pending_upload.discard(user_id)
                cleared = True
            if user_id in self._pending_action:
                self._pending_action.discard(user_id)
                cleared = True
            if user_id in self._pending_delete_action:
                self._pending_delete_action.discard(user_id)
                cleared = True
            await event.respond("✅ Cancelled pending input." if cleared else "Nothing to cancel.")

        @self.client.on(events.NewMessage(pattern="/settings"))
        async def show_settings(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            is_admin = user_id in self._config.admin_chat_ids

            summary = self._build_settings_summary(user_id)
            buttons = self._build_main_category_buttons(is_admin)
            await event.respond(summary, parse_mode="markdown", buttons=buttons)

        @self.client.on(events.NewMessage(pattern="/set_variable"))
        async def set_variable(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            parts = event.text.split()
            if len(parts) == 3:
                _, name, val = parts
                if name not in USER_CONFIGURABLE_KEYS:
                    await event.respond(f"❌ `{name}` is not a user-configurable variable. Available: {', '.join(sorted(USER_CONFIGURABLE_KEYS))}")
                    return
                self.db.save_user_config(user_id, name, val)
                await event.respond(f"✅ {name} set to {val}")
            else:
                # Compact version — prefer the rich /settings menu for most users.
                user_config = self.db.load_user_config(user_id)
                buttons = []
                row = []
                for var in sorted(USER_CONFIGURABLE_KEYS):
                    if var == "schedule":
                        continue
                    suffix = " (override)" if var in user_config else ""
                    row.append(KeyboardButtonCallback(
                        text=f"{var}{suffix}",
                        data=f"setvar-{var}".encode(),
                    ))
                    if len(row) == 2:
                        buttons.append(row)
                        row = []
                if row:
                    buttons.append(row)
                await event.respond(
                    "Select variable (or better: use /settings for the new menu). Direct syntax also works:\n/set_variable KEY value",
                    buttons=buttons,
                )

        @self.client.on(events.NewMessage(pattern="/delete_variable"))
        async def delete_variable(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            user_config = self.db.load_user_config(user_id)
            variables = [k for k in user_config if k in USER_CONFIGURABLE_KEYS]
            if not variables:
                await event.respond("No user variables to delete")
                return
            buttons = []
            for var in sorted(variables):
                buttons.append([KeyboardButtonCallback(
                    text=var,
                    data=f"deletevar-{var}".encode(),
                )])
            await event.respond(
                "Select variable to delete:",
                buttons=buttons,
            )

        @self.client.on(events.NewMessage(pattern="/set_global_variable"))
        async def set_global_variable(event):
            await self._check_admin(event)
            parts = event.text.split()
            if len(parts) == 3:
                _, name, val = parts
                if name not in ALL_CONFIGURABLE_KEYS:
                    await event.respond(f"❌ `{name}` is not a configurable variable. Available: {', '.join(sorted(ALL_CONFIGURABLE_KEYS))}")
                    return
                converted = convert_value(name, val)
                self.db.set_global_default(name, converted)
                await event.respond(f"✅ Global default {name} set to {converted}")
            else:
                global_config = self.db.list_global_defaults()
                buttons = []
                for var in sorted(ALL_CONFIGURABLE_KEYS):
                    suffix = f" = {global_config[var]}" if var in global_config else " (not set)"
                    tier = "🔒" if var in ADMIN_ONLY_KEYS else "👤"
                    buttons.append([KeyboardButtonCallback(
                        text=f"{tier} {var}{suffix}",
                        data=f"setglobalvar-{var}".encode(),
                    )])
                await event.respond(
                    "Select global variable to change:",
                    buttons=buttons,
                )

        @self.client.on(events.NewMessage(pattern="/delete_global_variable"))
        async def delete_global_variable(event):
            await self._check_admin(event)
            global_config = self.db.list_global_defaults()
            if not global_config:
                await event.respond("No global variables to delete")
                return
            buttons = []
            for var in sorted(global_config.keys()):
                tier = "🔒" if var in ADMIN_ONLY_KEYS else "👤"
                buttons.append([KeyboardButtonCallback(
                    text=f"{tier} {var} = {global_config[var]}",
                    data=f"deleteglobalvar-{var}".encode(),
                )])
            await event.respond(
                "Select global variable to delete:",
                buttons=buttons,
            )

        @self.client.on(events.NewMessage(pattern="/update"))
        async def manual_update(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            result_string = await self._update_avatar(user_id)
            await event.respond(result_string)

        @self.client.on(events.NewMessage(pattern="/upload"))
        async def upload_command(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            self._pending_upload.add(user_id)
            await event.respond("📸 Please send your base image (photo).")

        @self.client.on(events.NewMessage(pattern="/schedule"))
        async def show_schedule(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            schedule = self.db.load_schedule(user_id)
            if not schedule:
                await event.respond("No scheduled times set")
                return
            jobs = "\n".join(str(job) for job in self.scheduler.get_jobs() if job.id.startswith(f"avatar_{user_id}_"))
            await event.respond("Scheduled update times:\n" + "\n".join(schedule) + "\n\n" + jobs)

        @self.client.on(events.NewMessage(pattern="/add_time"))
        async def add_schedule(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            await event.respond("Please send the new time in HH:MM format")
            self._pending_time.add(user_id)

        @self.client.on(events.NewMessage(pattern="/delete_time"))
        async def remove_schedule(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            try:
                schedule = self.db.load_schedule(user_id)
                if not schedule:
                    await event.respond("No scheduled times to remove")
                    return

                buttons = []
                for time_str in schedule:
                    buttons.append([KeyboardButtonCallback(
                        text=time_str,
                        data=f"deletetime-{time_str}".encode(),
                    )])
                await event.respond(
                    "Select time to remove:",
                    buttons=buttons,
                )
            except Exception as e:
                await event.respond(f"❌ Error: {str(e)}")

        @self.client.on(events.NewMessage(pattern="/logs"))
        async def logs_command(event):
            await self._check_admin(event)
            parts = event.text.split()
            num = int(parts[1]) if len(parts) > 1 else 50
            logs = "\n".join(get_recent_logs(num))[-4096:]
            await event.respond(logs)

        @self.client.on(events.NewMessage(pattern="/weather"))
        async def current_weather(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            lat = self._get_effective_value(user_id, "latitude")
            lon = self._get_effective_value(user_id, "longitude")
            tz = self._get_effective_value(user_id, "timezone")
            weather_override = self._get_effective_value(user_id, "weather")
            weather = await self.weather_descriptor.get_forecast(
                latitude=float(lat) if lat else None,
                longitude=float(lon) if lon else None,
                timezone=tz,
                weather_override=weather_override,
            )
            await event.respond(f"```{json.dumps(weather)}```")

        @self.client.on(events.NewMessage(pattern="/video_mode"))
        async def video_mode_command(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            parts = event.text.split()
            if len(parts) == 2 and parts[1] in ("auto", "never"):
                self.db.save_user_config(user_id, "video_mode", parts[1])
                await event.respond(f"✅ video_mode set to {parts[1]}")
            else:
                current = self._get_effective_value(user_id, "video_mode") or "auto"
                await event.respond(
                    f"Current video_mode: {current}\n\n"
                    "Usage: /video_mode <auto|never>\n\n"
                    "• `auto` — generate video on holidays and extreme weather\n"
                    "• `never` — always generate static images",
                    parse_mode="markdown",
                )

        @self.client.on(events.NewMessage(pattern="/set_action"))
        async def set_action(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            text = event.text.strip()
            try:
                parts = shlex.split(text)
            except ValueError:
                parts = text.split()
            # after command: <type> <code> <action...>
            if len(parts) < 4 or parts[1] not in ("weather", "holiday"):
                await event.respond(
                    "Usage: /set_action <weather|holiday> <code_or_name> <action description>\n"
                    "Example: /set_action weather 95 \"lightning flash, user flinches\"\n"
                    "For names with spaces: /set_action holiday \"New Year's Day\" \"fireworks\""
                )
                return
            action_type = parts[1]
            key = parts[2]
            action_text = " ".join(parts[3:])
            await self._apply_video_action(user_id, action_type, key, action_text, event)

        @self.client.on(events.NewMessage(pattern="/delete_action"))
        async def delete_action(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            text = event.text.strip()
            try:
                parts = shlex.split(text)
            except ValueError:
                parts = text.split()
            if len(parts) < 3 or parts[1] not in ("weather", "holiday"):
                await event.respond(
                    "Usage: /delete_action <weather|holiday> <code_or_name>\n"
                    "For names with spaces: /delete_action holiday \"New Year's Day\""
                )
                return
            action_type = parts[1]
            key = parts[2]
            await self._delete_video_action(user_id, action_type, key, event)

        @self.client.on(events.NewMessage(pattern="/connection"))
        async def show_connection(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            connection = self.db.load_connection(user_id)
            if connection:
                await event.respond(f"Business connection active:\nConnection ID: {connection['connection_id']}\nUser ID: {connection['user_id']}")
            else:
                await event.respond("No business connection found. Connect the bot via Settings > Chat Automation in Telegram.")

        @self.client.on(events.NewMessage(pattern="/grant"))
        async def grant_user(event):
            await self._check_admin(event)
            parts = event.text.split()
            if len(parts) != 2:
                await event.respond("Usage: /grant <user_id>")
                return
            try:
                user_id = int(parts[1])
            except ValueError:
                await event.respond("❌ Invalid user ID")
                return
            self.db.grant(user_id)
            self._restore_user_schedule(user_id)
            await event.respond(f"✅ Granted access to user {user_id}")
            try:
                await self.client.send_message(user_id, "✅ You have been granted access to the bot! Use /start to begin.")
            except Exception:
                logger.warning(f"Could not notify user {user_id} about grant")

        @self.client.on(events.NewMessage(pattern="/revoke"))
        async def revoke_user(event):
            await self._check_admin(event)
            parts = event.text.split()
            if len(parts) != 2:
                await event.respond("Usage: /revoke <user_id>")
                return
            try:
                user_id = int(parts[1])
            except ValueError:
                await event.respond("❌ Invalid user ID")
                return
            self.db.revoke(user_id)
            self._remove_user_schedule(user_id)
            await event.respond(f"✅ Revoked access from user {user_id}")
            try:
                await self.client.send_message(user_id, "⛔ Your access to the bot has been revoked.")
            except Exception:
                logger.warning(f"Could not notify user {user_id} about revocation")

        @self.client.on(events.NewMessage(pattern="/list_users"))
        async def list_users(event):
            await self._check_admin(event)
            allowed = self.db.list_allowed()
            if not allowed:
                await event.respond("No users with access.")
                return
            lines = []
            for uid in allowed:
                has_conn = "✅" if self.db.load_connection(uid) else "❌"
                has_img = "✅" if self.db.has_base_image(uid) else "❌"
                is_admin = " 👑" if self.db.is_admin(uid) else ""
                lines.append(f"• {uid}{is_admin} | Connection: {has_conn} | Image: {has_img}")
            await event.respond("Users with access:\n" + "\n".join(lines))

    async def _handle_photo_upload(self, event, user_id: int):
        if not event.photo:
            await event.respond("❌ Please send a photo as your base image.")
            return
        try:
            from io import BytesIO
            buf = BytesIO()
            await event.download_media(file=buf)
            await self.db.save_base_image_bytes(user_id, buf.getvalue())
            await event.respond("✅ Base image uploaded successfully!")
        except Exception as e:
            logger.exception(f"Failed to save base image for user {user_id}")
            await event.respond(f"❌ Failed to save image: {str(e)}")

    async def _setup_menu(self):
        commands = [
            ("start", "Start bot"),
            ("help", "Show help message"),
            ("settings", "Interactive settings menu (recommended)"),
            ("update", "Force avatar update now"),
            ("upload", "Upload base image"),
            ("video_mode", "Set video generation mode"),
            ("schedule", "Show your update schedule"),
            ("add_time", "Add new update time (HH:MM)"),
            ("delete_time", "Delete update time (HH:MM)"),
            ("connection", "Show your business connection"),
            ("weather", "Show current weather"),
            # power-user / advanced still available:
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
        await self.client(SetBotCommandsRequest(
            scope=BotCommandScopeDefault(),
            lang_code="en",
            commands=[BotCommand(*cmd) for cmd in commands + admin_commands],
        ))

    async def _send_help(self, event):
        help_text = """🤖 Avatar Updater Bot Commands:

📸 Setup:
/upload - Upload base image
/connection - Show business connection status
/start - Connect via Settings > Chat Automation

⚙️ Settings (new improved UI):
/settings — Browse & edit by categories (📍 Location, ✍️ Prompts, 🎥 Video, 📅 Schedule, etc.)
/set_variable KEY VALUE — Direct set (power users)
/set_action <weather|holiday> CODE "action text" — Easy edit for video triggers
/delete_action <weather|holiday> CODE — Remove a video action
/cancel — Abort any pending value input
/delete_variable — (kept for compatibility)

🔄 Updates:
/update - Force update now
/video_mode - Set video generation mode (auto/never)
/schedule - Show update schedule
/add_time - Add new update time
/delete_time - Delete update time

🌐 Other:
/weather - Show current weather
/help - Show this message

👑 Admin:
/grant <user_id> - Grant access
/revoke <user_id> - Revoke access
/list_users - List all users
/set_global_variable - Set global default
/logs - Show recent logs"""
        await event.respond(help_text)

    def _validate_time(self, time_str: str) -> bool:
        try:
            datetime.strptime(time_str, "%H:%M")
            return True
        except ValueError:
            return False

    def _resolve_image_params(self, user_id: int) -> dict:
        image_generator = self._get_admin_value("image_generator")
        if isinstance(image_generator, str):
            try:
                image_generator = ImageGenerators(image_generator)
            except ValueError:
                image_generator = None
        return {
            "image_generator": image_generator,
            "polza_model": self._get_admin_value("polza_model"),
            "style": self._get_admin_value("style"),
            "image_cfg_scale": self._get_admin_value("image_cfg_scale"),
            "image_url": self._get_admin_value("image_url"),
            # Hermes / xAI via Hermes token
            "hermes_auth_path": self._get_admin_value("hermes_auth_path"),
            "hermes_xai_image_model": self._get_admin_value("hermes_xai_image_model"),
            "xai_auth_path": self._get_admin_value("xai_auth_path"),
        }

    async def _update_avatar(self, user_id: int) -> str:
        if not self.db.is_allowed(user_id):
            logger.warning(f"Skipping scheduled update for {user_id}: access not granted")
            return "Access not granted"
        if not self.db.load_connection(user_id):
            logger.warning(f"Skipping scheduled update for {user_id}: no business connection")
            return "No business connection"
        if not self.db.has_base_image(user_id):
            logger.warning(f"Skipping scheduled update for {user_id}: no base image")
            return "No base image uploaded. Use /upload to send one."
        if user_id in self._running_jobs:
            logger.info(f"Job already running for user {user_id}")
            return "Update already in progress for you"
        self._running_jobs.add(user_id)
        try:
            weather = await self._get_weather(user_id)
            use_video, weather_code = await self._should_generate_video(weather, user_id)
            if use_video:
                ref_prompt = await self._prepare_prompt(user_id, weather)
                image_params = self._resolve_image_params(user_id)
                ref_cache_hash = self.db.compute_cache_hash(user_id, ref_prompt, mode="image")
                ref_cached = self.db.check_cache(user_id, ref_cache_hash, mode="image")
                if ref_cached:
                    ref_image_path = ref_cached
                else:
                    ref_output_path = str(self.db.get_cache_path(user_id, ref_cache_hash, mode="image"))
                    img_generator = get_image_generator(
                        self._config,
                        image_generator=image_params["image_generator"],
                        polza_model=image_params["polza_model"],
                        style=image_params["style"],
                        image_cfg_scale=image_params["image_cfg_scale"],
                        image_url=image_params["image_url"],
                        hermes_auth_path=image_params.get("hermes_auth_path"),
                        hermes_xai_image_model=image_params.get("hermes_xai_image_model"),
                        xai_auth_path=image_params.get("xai_auth_path"),
                    )
                    ref_image_path = await img_generator.generate_and_save_image(
                        ref_prompt, self.db.get_base_image_path(user_id), ref_output_path
                    )
                video_prompt = await self._prepare_video_prompt(user_id, weather, weather_code)
                video_gen = self._get_admin_value("video_generator")
                if isinstance(video_gen, str):
                    try:
                        video_gen = VideoGenerators(video_gen)
                    except ValueError:
                        video_gen = None
                await self.updater.async_update_video_avatar(
                    video_prompt, user_id,
                    video_generator=video_gen,
                    reference_image_path=ref_image_path,
                    hermes_auth_path=self._get_admin_value("hermes_auth_path"),
                    hermes_xai_video_model=self._get_admin_value("hermes_xai_video_model"),
                    xai_auth_path=self._get_admin_value("xai_auth_path"),
                )
                logger.info(f"User {user_id}: Video avatar updated!")
                return "✅ Video avatar updated!"
            else:
                prompt = await self._prepare_prompt(user_id, weather)
                image_params = self._resolve_image_params(user_id)
                await self.updater.async_update_avatar(prompt, user_id, **image_params)
                logger.info(f"User {user_id}: Avatar updated!")
                return "✅ Avatar updated!"
        except Exception as e:
            error = f"Error while updating avatar: {str(e)}"
            logger.exception(e)
            return error
        finally:
            self._running_jobs.discard(user_id)

    async def _prepare_prompt(self, user_id: int, weather: dict | None = None) -> str:
        place = self._get_effective_value(user_id, "place") or ""
        holidays = self._get_effective_value(user_id, "holidays")
        prompt_template = self._get_effective_value(user_id, "prompt_text")

        if weather is None:
            weather = await self._get_weather(user_id)
        prompt = prompt_template or ""
        weather = {**(weather or {}), "place": place}
        holiday = self.holiday_checker.get_today_holiday(holidays)
        if holiday:
            weather["clothing"] = self.holiday_checker.get_clothing(holidays)
            weather["environmental_details"] = self.holiday_checker.get_details(holidays)
        for key, val in weather.items():
            prompt = prompt.replace("{" + key + "}", str(val))
        logger.info(f"User {user_id}: Prepared prompt: {prompt}")
        return prompt

    async def _get_weather(self, user_id: int) -> dict | None:
        lat = self._get_effective_value(user_id, "latitude")
        lon = self._get_effective_value(user_id, "longitude")
        tz = self._get_effective_value(user_id, "timezone")
        weather_override = self._get_effective_value(user_id, "weather")
        try:
            return await self.weather_descriptor.get_forecast(
                latitude=float(lat) if lat else None,
                longitude=float(lon) if lon else None,
                timezone=tz,
                weather_override=weather_override,
            )
        except Exception:
            logger.warning(f"Could not fetch weather for user {user_id}")
            return None

    async def _should_generate_video(self, weather: dict | None, user_id: int) -> tuple[bool, str | None]:
        video_mode = self._get_effective_value(user_id, "video_mode")
        if video_mode == "never":
            return False, None

        video_actions = self._get_effective_value(user_id, "video_actions") or {}
        if isinstance(video_actions, str):
            import json as _json
            video_actions = _json.loads(video_actions)

        holidays = self._get_effective_value(user_id, "holidays")
        holiday = self.holiday_checker.get_today_holiday(holidays)

        holiday_actions = video_actions.get("holidays", {})
        if holiday and holiday in holiday_actions:
            return True, str(weather.get("weather_code", "")) if weather else None

        weather_actions = video_actions.get("weather", {})
        if weather:
            weather_code = str(weather.get("weather_code", ""))
            if weather_code in weather_actions:
                return True, weather_code

        return False, str(weather.get("weather_code", "")) if weather else None

    async def _prepare_video_prompt(self, user_id: int, weather: dict | None, weather_code: str | None) -> str:
        place = self._get_effective_value(user_id, "place") or ""
        holidays = self._get_effective_value(user_id, "holidays")
        prompt_template = self._get_effective_value(user_id, "video_prompt_text") or "{action}"

        if weather is None:
            weather = await self._get_weather(user_id) or {}
        holiday = self.holiday_checker.get_today_holiday(holidays)

        video_actions = self._get_effective_value(user_id, "video_actions") or {}
        if isinstance(video_actions, str):
            import json as _json
            video_actions = _json.loads(video_actions)

        action = ""
        if holiday:
            holiday_actions = video_actions.get("holidays", {})
            action = holiday_actions.get(holiday, "")
        if not action and weather_code:
            weather_actions = video_actions.get("weather", {})
            action = weather_actions.get(weather_code, "")

        weather = {**weather, "place": place, "action": action}
        if holiday:
            weather["clothing"] = self.holiday_checker.get_clothing(holidays)
            weather["environmental_details"] = self.holiday_checker.get_details(holidays)

        prompt = prompt_template
        for key, val in weather.items():
            prompt = prompt.replace("{" + key + "}", str(val))
        logger.info(f"User {user_id}: Prepared video prompt: {prompt}")
        return prompt

    def _restore_user_schedule(self, user_id: int):
        schedule = self.db.load_schedule(user_id)
        for job in self.scheduler.get_jobs():
            if job.id.startswith(f"avatar_{user_id}_"):
                self.scheduler.remove_job(job.id)
        for time_str in schedule:
            hour, minute = map(int, time_str.split(":"))
            self.scheduler.add_job(
                self._update_avatar,
                "cron",
                hour=hour,
                minute=minute,
                timezone="UTC",
                max_instances=1,
                args=[user_id],
                id=f"avatar_{user_id}_{time_str}",
            )
        if schedule and self.scheduler.state == 0:
            self.scheduler.start()

    def _remove_user_schedule(self, user_id: int):
        for job in self.scheduler.get_jobs():
            if job.id.startswith(f"avatar_{user_id}_"):
                self.scheduler.remove_job(job.id)

    def restore_all_schedules(self):
        for user_id in self.db.list_allowed():
            self._restore_user_schedule(user_id)

    def _restart_scheduler(self, user_id: int):
        self._restore_user_schedule(user_id)