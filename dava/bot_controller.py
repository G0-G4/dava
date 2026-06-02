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

from dava.auth import AuthManager
from dava.avatar_updater import AvatarUpdater
from dava.config import Config
from dava.holidays import HolidayChecker
from dava.logs import get_recent_logs
from dava.user_store import UserStore
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
    def __init__(self, updater: AvatarUpdater, weather_descriptor: WeatherDescriptor, config: Config, auth: AuthManager, users: UserStore):
        self.updater = updater
        self.weather_descriptor = weather_descriptor
        self.auth = auth
        self.users = users
        self.client = TelegramClient("bot_session", config.api_id, config.api_hash)
        if PROXY := os.getenv("PROXY"):
            self.client.set_proxy(parse_proxy_url(PROXY))
        self.scheduler = AsyncIOScheduler()
        self._config = config
        self._pending_var: dict[int, str] = {}
        self._pending_time: set[int] = set()
        self._pending_upload: set[int] = set()
        self._running_jobs: set[int] = set()
        self.holiday_checker = HolidayChecker(config)
        self._setup_handlers()

    async def start(self):
        await self.client.start(bot_token=self._config.bot_token)
        await self._setup_menu()
        await self.client.run_until_disconnected()

    async def _check_admin(self, event):
        if not self.auth.is_admin(event.chat_id):
            await event.respond("⛔ This command is for admins only.")
            raise RuntimeError(f"Non-admin user {event.chat_id} tried admin command")

    async def _check_allowed(self, event):
        if not self.auth.is_allowed(event.chat_id):
            await event.respond("⛔ Access not granted. Please contact the admin to get access.")
            raise RuntimeError(f"Unauthorized user {event.chat_id} tried to use bot")

    def _get_effective_value(self, user_id: int, key: str):
        return self.users.get_effective_value(user_id, key, getattr(self._config, key, None))

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
            self.users.save_connection(
                user_id=user_id,
                connection_id=connection.connection_id,
                tg_user_id=connection.user_id,
                rights=rights,
            )
            logger.info(f"Business connection established: {connection.connection_id} (user_id={user_id})")

            if self.auth.is_allowed(user_id):
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
                for admin_id in self.auth.list_allowed():
                    if self.auth.is_admin(admin_id):
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
                self.users.delete_user_config_key(user_id, var_name)
                await event.respond(f"✅ {var_name} has been deleted")
            elif event.data.startswith(b"deletetime-"):
                time_str = event.data.decode().split("-")[1]
                schedule = self.users.load_schedule(user_id)
                if time_str in schedule:
                    schedule.remove(time_str)
                    self.users.save_schedule(user_id, schedule)
                    self._restart_scheduler(user_id)
                    await event.respond(f"⏰ Removed {time_str} from schedule")
                else:
                    await event.respond("⏰ Time not found in schedule")

        @self.client.on(events.NewMessage())
        async def handle_value_input(event):
            user_id = event.chat_id
            if not self.auth.is_allowed(user_id):
                return
            try:
                if user_id in self._pending_var and not event.text.startswith("/"):
                    var_name = self._pending_var.pop(user_id)
                    new_value = event.text
                    self.users.save_user_config(user_id, var_name, new_value)
                    await event.respond(f"✅ {var_name} set to {new_value}")
                elif user_id in self._pending_time and not event.text.startswith("/"):
                    self._pending_time.discard(user_id)
                    time_str = event.text.strip()
                    if not self._validate_time(time_str):
                        await event.respond("❌ Invalid time format. Use HH:MM")
                        return

                    schedule = self.users.load_schedule(user_id)
                    if time_str not in schedule:
                        schedule.append(time_str)
                        self.users.save_schedule(user_id, schedule)
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
            user_config = self.users.load_user_config(user_id)
            global_vars = self._config.all_variables()
            lines = []
            for k, v in global_vars.items():
                user_val = user_config.get(k)
                if user_val is not None:
                    lines.append(f"🔹 {k}: `{user_val}` (override)")
                else:
                    lines.append(f"🔹 {k}: `{v}` (default)")
            for k, v in user_config.items():
                if k not in global_vars and k != "schedule":
                    lines.append(f"🔹 {k}: `{v}`")
            await event.respond(
                "Your settings (click to copy):\n\n" + "\n".join(lines),
                parse_mode="markdown",
            )

        @self.client.on(events.NewMessage(pattern="/set_variable"))
        async def set_variable(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            parts = event.text.split()
            if len(parts) == 3:
                _, name, val = parts
                self.users.save_user_config(user_id, name, val)
                await event.respond(f"✅ {name} set to {val}")
            else:
                user_config = self.users.load_user_config(user_id)
                global_vars = self._config.all_variables()
                all_keys = list(global_vars.keys()) + [k for k in user_config if k not in global_vars and k != "schedule"]
                buttons = []
                for var in all_keys:
                    buttons.append([KeyboardButtonCallback(
                        text=var,
                        data=f"setvar-{var}".encode(),
                    )])
                await event.respond(
                    "Select variable to change:",
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
            schedule = self.users.load_schedule(user_id)
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
                schedule = self.users.load_schedule(user_id)
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

        @self.client.on(events.NewMessage(pattern="/delete_variable"))
        async def delete_variable(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            user_config = self.users.load_user_config(user_id)
            variables = [k for k in user_config if k != "schedule"]
            if not variables:
                await event.respond("No user variables to delete")
                return
            buttons = []
            for var in variables:
                buttons.append([KeyboardButtonCallback(
                    text=var,
                    data=f"deletevar-{var}".encode(),
                )])
            await event.respond(
                "Select variable to delete:",
                buttons=buttons,
            )

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

        @self.client.on(events.NewMessage(pattern="/connection"))
        async def show_connection(event):
            await self._check_allowed(event)
            user_id = event.chat_id
            connection = self.users.load_connection(user_id)
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
            self.auth.grant(user_id)
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
            self.auth.revoke(user_id)
            self._remove_user_schedule(user_id)
            await event.respond(f"✅ Revoked access from user {user_id}")
            try:
                await self.client.send_message(user_id, "⛔ Your access to the bot has been revoked.")
            except Exception:
                logger.warning(f"Could not notify user {user_id} about revocation")

        @self.client.on(events.NewMessage(pattern="/list_users"))
        async def list_users(event):
            await self._check_admin(event)
            allowed = self.auth.list_allowed()
            if not allowed:
                await event.respond("No users with access.")
                return
            lines = []
            for uid in allowed:
                has_conn = "✅" if self.users.load_connection(uid) else "❌"
                has_img = "✅" if self.users.has_base_image(uid) else "❌"
                is_admin = " 👑" if self.auth.is_admin(uid) else ""
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
            await self.users.save_base_image_bytes(user_id, buf.getvalue())
            await event.respond("✅ Base image uploaded successfully!")
        except Exception as e:
            logger.exception(f"Failed to save base image for user {user_id}")
            await event.respond(f"❌ Failed to save image: {str(e)}")

    async def _setup_menu(self):
        commands = [
            ("start", "Start bot"),
            ("help", "Show help message"),
            ("settings", "Show your settings"),
            ("set_variable", "Set your config variable"),
            ("delete_variable", "Delete your config variable"),
            ("update", "Force avatar update now"),
            ("upload", "Upload base image"),
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
/logs - Show recent logs"""
        await event.respond(help_text)

    def _validate_time(self, time_str: str) -> bool:
        try:
            datetime.strptime(time_str, "%H:%M")
            return True
        except ValueError:
            return False

    async def _update_avatar(self, user_id: int) -> str:
        if user_id in self._running_jobs:
            logger.info(f"Job already running for user {user_id}")
            return "Update already in progress for you"
        prompt = await self._prepare_prompt(user_id)
        previous_prompt = self._get_effective_value(user_id, "previous_prompt_text")
        if previous_prompt == prompt:
            message = "Prompt hasn't changed, no update needed"
            logger.info(f"User {user_id}: {message}")
            return message
        try:
            self._running_jobs.add(user_id)
            await self.updater.async_update_avatar(prompt, user_id)
            self.users.save_user_config(user_id, "previous_prompt_text", prompt)
            logger.info(f"User {user_id}: Avatar updated!")
            return "✅ Avatar updated!"
        except Exception as e:
            error = f"Error while updating avatar: {str(e)}"
            logger.exception(e)
            return error
        finally:
            self._running_jobs.discard(user_id)

    async def _prepare_prompt(self, user_id: int) -> str:
        lat = self._get_effective_value(user_id, "latitude")
        lon = self._get_effective_value(user_id, "longitude")
        tz = self._get_effective_value(user_id, "timezone")
        place = self._get_effective_value(user_id, "place") or ""
        weather_override = self._get_effective_value(user_id, "weather")
        holidays = self._get_effective_value(user_id, "holidays")
        prompt_template = self._get_effective_value(user_id, "prompt_text")

        weather = await self.weather_descriptor.get_forecast(
            latitude=float(lat) if lat else None,
            longitude=float(lon) if lon else None,
            timezone=tz,
            weather_override=weather_override,
        )
        prompt = prompt_template or ""
        weather = {**weather, "place": place}
        holiday = self.holiday_checker.get_today_holiday(holidays)
        if holiday:
            weather["clothing"] = self.holiday_checker.get_clothing(holidays)
            weather["environmental_details"] = self.holiday_checker.get_details(holidays)
        for key, val in weather.items():
            prompt = prompt.replace("{" + key + "}", val)
        logger.info(f"User {user_id}: Prepared prompt: {prompt}")
        return prompt

    def _restore_user_schedule(self, user_id: int):
        schedule = self.users.load_schedule(user_id)
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
        for user_id in self.auth.list_allowed():
            self._restore_user_schedule(user_id)

    def _restart_scheduler(self, user_id: int):
        self._restore_user_schedule(user_id)