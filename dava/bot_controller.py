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
from dava.config import Config
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
    def __init__(self, updater: AvatarUpdater, weather_descriptor: WeatherDescriptor, config: Config):
        self.updater = updater
        self.weather_descriptor = weather_descriptor
        self.client = TelegramClient("bot_session", config.api_id, config.api_hash)
        if PROXY := os.getenv("PROXY"):
            self.client.set_proxy(parse_proxy_url(PROXY))
        self.scheduler = AsyncIOScheduler()
        self._config = config
        self._pending_var = None
        self._pending_time = False
        self._setup_handlers()
        self._load_and_start_schedule()
        self._is_job_running = False
        self.holiday_checker = HolidayChecker(config)

    async def start(self):
        await self.client.start(bot_token=self._config.bot_token)
        connection = self._config.load_connection()
        if connection:
            logger.info(f"Loaded saved business connection: {connection['connection_id']}")
        else:
            logger.info("No saved business connection. Connect the bot via Settings > Chat Automation in Telegram.")
        await self._setup_menu()
        await self.client.run_until_disconnected()

    async def _check_allowed_chat(self, event):
        if event.chat_id != self._config.allowed_chat_id:
            raise RuntimeError("unknow user is trying to change your avatar!")

    def _setup_handlers(self):
        self._pending_var = None

        @self.client.on(events.Raw(types=tl_types.UpdateBotBusinessConnect))
        async def business_connect_handler(update):
            connection = update.connection
            if hasattr(connection, "connection_id") and hasattr(connection, "user_id"):
                rights = None
                if hasattr(connection, "rights") and connection.rights:
                    rights = {
                        "edit_profile_photo": getattr(connection.rights, "edit_profile_photo", False),
                    }
                self._config.save_connection(
                    connection_id=connection.connection_id,
                    user_id=connection.user_id,
                    rights=rights,
                )
                logger.info(f"Business connection established: {connection.connection_id} (user_id={connection.user_id})")

                if connection.user_id != self._config.allowed_chat_id:
                    return

                has_photo_right = rights and rights.get("edit_profile_photo")
                status = "with" if has_photo_right else "without"
                await self.client.send_message(
                    self._config.allowed_chat_id,
                    f"Business connection {status} profile photo editing rights.",
                )

        @self.client.on(events.CallbackQuery())
        async def callback_handler(event):
            await self._check_allowed_chat(event)
            if event.data.startswith(b"setvar-"):
                var_name = event.data.decode().split("-")[1]
                self._pending_var = var_name
                await event.respond(f"Please send the new value for {var_name}")
            elif event.data.startswith(b"deletevar-"):
                var_name = event.data.decode().split("-")[1]
                del self._config[var_name]
                await event.respond(f"✅ {var_name} has been deleted")
            elif event.data.startswith(b"deletetime-"):
                time_str = event.data.decode().split("-")[1]
                schedule = self._config.load_schedule()
                if time_str in schedule:
                    schedule.remove(time_str)
                    self._config.save_schedule(schedule)
                    self._restart_scheduler()
                    await event.respond(f"⏰ Removed {time_str} from schedule")
                else:
                    await event.respond("⏰ Time not found in schedule")

        @self.client.on(events.NewMessage())
        async def handle_value_input(event):
            await self._check_allowed_chat(event)
            try:
                if self._pending_var and not event.text.startswith("/"):
                    var_name = self._pending_var
                    new_value = event.text
                    self._config[var_name] = new_value
                    self._pending_var = None
                    await event.respond(f"✅ {var_name} set to {new_value}")
                elif self._pending_time and not event.text.startswith("/"):
                    time_str = event.text.strip()
                    if not self._validate_time(time_str):
                        await event.respond("❌ Invalid time format. Use HH:MM")
                        return

                    schedule = self._config.load_schedule()
                    if time_str not in schedule:
                        schedule.append(time_str)
                        self._config.save_schedule(schedule)
                        self._restart_scheduler()
                        await event.respond(f"⏰ Added {time_str} to schedule")
                    else:
                        await event.respond("⏰ Time already exists in schedule")
            except Exception as e:
                await event.respond(f"❌ Error: {str(e)}")
            finally:
                self._pending_var = None
                self._pending_time = False

        @self.client.on(events.NewMessage(pattern="/start"))
        async def start(event):
            await self._check_allowed_chat(event)
            await self._send_help(event)

        @self.client.on(events.NewMessage(pattern="/help"))
        async def help(event):
            await self._check_allowed_chat(event)
            await self._send_help(event)

        @self.client.on(events.NewMessage(pattern="/settings"))
        async def show_settings(event):
            await self._check_allowed_chat(event)
            settings = "\n".join(
                f"🔹 {k}: `{v}`"
                for k, v in self._config.all_variables().items()
            )
            await event.respond(
                "Current settings (click to copy):\n\n" + settings,
                parse_mode="markdown",
            )

        @self.client.on(events.NewMessage(pattern="/set_variable"))
        async def set_variable(event):
            await self._check_allowed_chat(event)
            parts = event.text.split()
            if len(parts) == 3:
                _, name, val = parts
                self._config[name] = val
                await event.respond(f"{name} set to {val}")
            else:
                variables = self._config.all_variables().keys()
                buttons = []
                for var in variables:
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
            await self._check_allowed_chat(event)
            result_string = await self._update_avatar()
            await event.respond(result_string)

        @self.client.on(events.NewMessage(pattern="/schedule"))
        async def show_schedule(event):
            await self._check_allowed_chat(event)
            schedule = self._config.load_schedule()
            if not schedule:
                await event.respond("No scheduled times set")
                return
            jobs = "\n".join((str(job) for job in self.scheduler.get_jobs()))
            await event.respond("Scheduled update times:\n" + "\n".join(schedule) + "\n\n" + jobs)

        @self.client.on(events.NewMessage(pattern="/add_time"))
        async def add_schedule(event):
            await self._check_allowed_chat(event)
            await event.respond("Please send the new time in HH:MM format")
            self._pending_time = True

        @self.client.on(events.NewMessage(pattern="/delete_time"))
        async def remove_schedule(event):
            await self._check_allowed_chat(event)
            try:
                schedule = self._config.load_schedule()
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
            await self._check_allowed_chat(event)
            variables = self._config.all_variables().keys()
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
            await self._check_allowed_chat(event)
            parts = event.text.split()
            num = int(parts[1]) if len(parts) > 1 else 50
            logs = "\n".join(get_recent_logs(num))[-4096:]
            await event.respond(logs)

        @self.client.on(events.NewMessage(pattern="/weather"))
        async def current_weather(event):
            await self._check_allowed_chat(event)
            weather = await self.weather_descriptor.get_forecast()
            await event.respond(f"```{json.dumps(weather)}```")

        @self.client.on(events.NewMessage(pattern="/connection"))
        async def show_connection(event):
            await self._check_allowed_chat(event)
            connection = self._config.load_connection()
            if connection:
                await event.respond(f"Business connection active:\nConnection ID: {connection['connection_id']}\nUser ID: {connection['user_id']}")
            else:
                await event.respond("No business connection found. Connect the bot via Settings > Chat Automation in Telegram.")

    async def _setup_menu(self):
        commands = [
            ("start", "Start bot"),
            ("help", "Show help message"),
            ("settings", "Show current settings"),
            ("set_variable", "Set config variable"),
            ("delete_variable", "Delete config variable"),
            ("update", "Force avatar update now"),
            ("schedule", "Show update schedule"),
            ("add_time", "Add new update time (HH:MM)"),
            ("delete_time", "Delete update time (HH:MM)"),
            ("logs", "Show recent logs"),
            ("connection", "Show business connection status"),
            ("weather", "Show current weather"),
        ]
        await self.client(SetBotCommandsRequest(
            scope=BotCommandScopeDefault(),
            lang_code="en",
            commands=[BotCommand(*cmd) for cmd in commands],
        ))

    async def _send_help(self, event):
        help_text = """🤖 Avatar Updater Bot Commands:
/settings - Show current settings
/set_variable - Set config variable
/delete_variable - Delete config variable
/schedule - Show update schedule
/add_time HH:MM - Add new update time
/delete_time HH:MM - Delete update time
/update - Force update now
/connection - Show business connection status
/help - Show this message
/weather - Show current weather

⚡ Setup: Connect this bot to your profile via
Settings > Chat Automation in Telegram."""
        logger.info(f"chat_id {event.chat_id}")
        await event.respond(help_text)

    def _validate_time(self, time_str: str) -> bool:
        try:
            datetime.strptime(time_str, "%H:%M")
            return True
        except ValueError:
            return False

    async def _update_avatar(self):
        if self._is_job_running:
            logger.info("job is already running")
            return "job is already running"
        prompt = await self.prepare_prompt()
        if self._config.previous_prompt_text == prompt:
            message = "prompt hasn't changed, no update needed"
            logger.info(message)
            return message
        try:
            self._is_job_running = True
            await self.updater.async_update_avatar(prompt)
            self._config["previous_prompt_text"] = prompt
            logger.info("Avatar updated!")
            return "✅ Avatar updated!"
        except Exception as e:
            error = f"error while updating avatar: {str(e)}"
            logger.exception(e)
            return error
        finally:
            self._is_job_running = False

    async def prepare_prompt(self):
        weather = await self.weather_descriptor.get_forecast()
        prompt = self._config.prompt_text
        weather = {**weather, "place": self._config.place}
        holiday = self.holiday_checker.get_today_holiday()
        if holiday:
            weather["clothing"] = self.holiday_checker.get_clothing()
            weather["environmental_details"] = self.holiday_checker.get_details()
        for key, val in weather.items():
            prompt = prompt.replace("{" + key + "}", val)
        logger.info(f"Prepared prompt: {prompt}")
        return prompt

    def _load_and_start_schedule(self):
        schedule = self._config.load_schedule()
        self.scheduler.remove_all_jobs()
        for time_str in schedule:
            hour, minute = map(int, time_str.split(":"))
            self.scheduler.add_job(
                self._update_avatar,
                "cron",
                hour=hour,
                minute=minute,
                timezone="UTC",
                max_instances=1,
            )
        if schedule and self.scheduler.state == 0:
            self.scheduler.start()

    def _restart_scheduler(self):
        self._load_and_start_schedule()