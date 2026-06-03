import json
import logging
import os
from datetime import datetime
from urllib.parse import urlparse

from telethon import TelegramClient, events
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault, KeyboardButtonCallback
from telethon.tl import types as tl_types
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from dava.avatar_updater import AvatarUpdater
from dava.config import Config, USER_CONFIGURABLE_KEYS, ADMIN_ONLY_KEYS, ALL_CONFIGURABLE_KEYS, ImageGenerators, Style, VideoGenerators, convert_value
from dava.db import Database
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

    def _get_effective_value(self, user_id: int, key: str):
        return self.db.get_effective_value(user_id, key)

    def _get_admin_value(self, key: str):
        return self.db.get_admin_value(key)

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

        @self.client.on(events.NewMessage(pattern="/settings"))
        async def show_settings(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            user_config = self.db.load_user_config(user_id)
            global_config = self.db.list_global_defaults()
            lines = []

            admin_lines = []
            for key in sorted(ADMIN_ONLY_KEYS):
                val = global_config.get(key)
                if val is not None:
                    admin_lines.append(f"⚙️ {key}: `{val}`")

            user_lines = []
            for key in sorted(USER_CONFIGURABLE_KEYS):
                if key in user_config and key != "schedule":
                    user_lines.append(f"🔹 {key}: `{user_config[key]}` (your override)")
                elif key in global_config:
                    user_lines.append(f"🔹 {key}: `{global_config[key]}` (default)")

            if admin_lines:
                lines.append("⚙️ Admin-only settings:")
                lines.extend(admin_lines)
            if user_lines:
                lines.append("")
                lines.append("👤 Your settings:")
                lines.extend(user_lines)
            for k, v in user_config.items():
                if k not in USER_CONFIGURABLE_KEYS and k not in ADMIN_ONLY_KEYS and k != "schedule":
                    lines.append(f"🔸 {k}: `{v}`")
            await event.respond(
                "\n".join(lines),
                parse_mode="markdown",
            )

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
                user_config = self.db.load_user_config(user_id)
                buttons = []
                for var in sorted(USER_CONFIGURABLE_KEYS):
                    suffix = " (override)" if var in user_config else ""
                    buttons.append([KeyboardButtonCallback(
                        text=f"{var}{suffix}",
                        data=f"setvar-{var}".encode(),
                    )])
                await event.respond(
                    "Select variable to change:",
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
            ("settings", "Show your settings"),
            ("set_variable", "Set config variable"),
            ("delete_variable", "Delete config variable"),
            ("update", "Force avatar update now"),
            ("upload", "Upload base image"),
            ("video_mode", "Set video generation mode"),
            ("schedule", "Show your update schedule"),
            ("add_time", "Add new update time (HH:MM)"),
            ("delete_time", "Delete update time (HH:MM)"),
            ("connection", "Show your business connection"),
            ("weather", "Show current weather"),
        ]
        admin_commands = [
            ("logs", "Show recent logs"),
            ("grant", "Grant access to user"),
            ("revoke", "Revoke access from user"),
            ("list_users", "List all users with access"),
            ("set_global_variable", "Set global config variable"),
            ("delete_global_variable", "Delete global config variable"),
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

⚙️ Settings:
/settings - Show your settings
/set_variable - Set config variable
/delete_variable - Delete config variable

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
/set_global_variable - Set global default variable
/delete_global_variable - Delete global default variable
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
                prompt = await self._prepare_video_prompt(user_id, weather, weather_code)
                video_gen = self._get_admin_value("video_generator")
                if isinstance(video_gen, str):
                    try:
                        video_gen = VideoGenerators(video_gen)
                    except ValueError:
                        video_gen = None
                await self.updater.async_update_video_avatar(
                    prompt, user_id, video_generator=video_gen,
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

        holidays = self._get_effective_value(user_id, "holidays")
        holiday = self.holiday_checker.get_today_holiday(holidays)

        if holiday:
            return True, str(weather.get("weather_code", "")) if weather else None

        extreme_codes = self._get_admin_value("extreme_weather_codes")
        if extreme_codes is None:
            extreme_codes = []
        elif isinstance(extreme_codes, str):
            import json as _json
            extreme_codes = _json.loads(extreme_codes)

        if weather:
            weather_code = str(weather.get("weather_code", ""))
            try:
                if int(weather_code) in extreme_codes:
                    return True, weather_code
            except (ValueError, TypeError):
                pass

        return False, str(weather.get("weather_code", "")) if weather else None

    async def _prepare_video_prompt(self, user_id: int, weather: dict | None, weather_code: str | None) -> str:
        place = self._get_effective_value(user_id, "place") or ""
        holidays = self._get_effective_value(user_id, "holidays")
        prompt_template = self._get_effective_value(user_id, "video_prompt_text") or "Animated portrait of a person centered in frame, {action}, {detailed_description}, {lighting_description}, {place}"

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