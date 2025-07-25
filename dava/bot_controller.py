import logging
from datetime import datetime

from telethon import TelegramClient, events
import telethon.tl.types
import telethon.tl.functions.bots
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from dava import AvatarUpdater
from dava.avatar_generator import AvatarGenerator
from dava.config import Config
from dava.logs import get_recent_logs
from dava.weather_descriptor import WeatherDescriptor

logger = logging.getLogger(__name__)

class BotController:
    def __init__(self, updater: AvatarUpdater, weather_descriptor: WeatherDescriptor, avatar_generator: AvatarGenerator, config: Config):
        self.updater = updater
        self.weather_descriptor = weather_descriptor
        self.avatar_generator = avatar_generator
        self.client = TelegramClient("bot_session", config.api_id, config.api_hash)
        self.scheduler = AsyncIOScheduler()
        self._config = config
        self._pending_var = None
        self._pending_time = False
        self._setup_handlers()
        self._load_and_start_schedule()
        self._is_job_running = False

    async def start(self):
        await self.client.start(bot_token=self._config.bot_token)
        await self._setup_menu()
        await self.client.run_until_disconnected()

    async def _check_allowed_chat(self, event):
        if event.chat_id != self._config.allowed_chat_id:
            raise RuntimeError("unknow user is trying to change your avatar!")

    def _setup_handlers(self):
        self._pending_var = None  # Add this line to track pending variable changes
        
        @self.client.on(events.CallbackQuery())
        async def callback_handler(event):
            await self._check_allowed_chat(event)
            if event.data.startswith(b'setvar-'):
                var_name = event.data.decode().split('-')[1]
                self._pending_var = var_name
                await event.respond(f"Please send the new value for {var_name}")
            elif event.data.startswith(b'deletevar-'):
                var_name = event.data.decode().split('-')[1]
                del self._config[var_name]
                await event.respond(f"✅ {var_name} has been deleted")
            elif event.data.startswith(b'deletetime-'):
                time_str = event.data.decode().split('-')[1]
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
                if self._pending_var and not event.text.startswith('/'):
                    var_name = self._pending_var
                    new_value = event.text
                    self._config[var_name] = new_value
                    self._pending_var = None
                    await event.respond(f"✅ {var_name} set to {new_value}")
                elif self._pending_time and not event.text.startswith('/'):
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

        @self.client.on(events.NewMessage(pattern='/start'))
        async def start(event):
            await self._check_allowed_chat(event)
            await self._send_help(event)

        @self.client.on(events.NewMessage(pattern='/help'))
        async def help(event):
            await self._check_allowed_chat(event)
            await self._send_help(event)

        @self.client.on(events.NewMessage(pattern='/settings'))
        async def show_settings(event):
            await self._check_allowed_chat(event)
            settings = "\n".join(
                f"🔹 {k}: `{v}`"  # Using backticks for monospace formatting
                for k, v in self._config.all_variables().items()
            )
            await event.respond(
                "Current settings (click to copy):\n\n" + settings,
                parse_mode='markdown'  # This enables the monospace formatting
            )

        @self.client.on(events.NewMessage(pattern='/set_variable'))
        async def set_variable(event):
            await self._check_allowed_chat(event)
            parts = event.text.split()
            if len(parts) == 3:
                # Old direct set behavior
                _, name, val = parts
                self._config[name] = val
                await event.respond(f"{name} set to {val}")
            else:
                # Show variable selection buttons
                variables = self._config.all_variables().keys()
                buttons = []
                for var in variables:
                    buttons.append([telethon.tl.types.KeyboardButtonCallback(
                        text=var,
                        data=f"setvar-{var}".encode()
                    )])
                await event.respond(
                    "Select variable to change:",
                    buttons=buttons
                )

        @self.client.on(events.NewMessage(pattern='/update'))
        async def manual_update(event):
            await self._check_allowed_chat(event)
            result_string = await self._update_avatar()
            await event.respond(result_string)

        @self.client.on(events.NewMessage(pattern='/schedule'))
        async def show_schedule(event):
            await self._check_allowed_chat(event)
            schedule = self._config.load_schedule()
            if not schedule:
                await event.respond("No scheduled times set")
                return
            jobs = "\n".join((str(job) for job in self.scheduler.get_jobs()))
            await event.respond("Scheduled update times:\n" + "\n".join(schedule) + "\n\n" + jobs)

        @self.client.on(events.NewMessage(pattern='/add_time'))
        async def add_schedule(event):
            await self._check_allowed_chat(event)
            await event.respond("Please send the new time in HH:MM format")
            self._pending_time = True  # Track that we're expecting a time input

        @self.client.on(events.NewMessage(pattern='/delete_time'))
        async def remove_schedule(event):
            await self._check_allowed_chat(event)
            try:
                schedule = self._config.load_schedule()
                if not schedule:
                    await event.respond("No scheduled times to remove")
                    return

                buttons = []
                for time_str in schedule:
                    buttons.append([telethon.tl.types.KeyboardButtonCallback(
                        text=time_str,
                        data=f"deletetime-{time_str}".encode()
                    )])
                await event.respond(
                    "Select time to remove:",
                    buttons=buttons
                )
            except Exception as e:
                await event.respond(f"❌ Error: {str(e)}")

        @self.client.on(events.NewMessage(pattern='/delete_variable'))
        async def delete_variable(event):
            await self._check_allowed_chat(event)
            variables = self._config.all_variables().keys()
            buttons = []
            for var in variables:
                buttons.append([telethon.tl.types.KeyboardButtonCallback(
                    text=var,
                    data=f"deletevar-{var}".encode()
                )])
            await event.respond(
                "Select variable to delete:",
                buttons=buttons
            )

        @self.client.on(events.NewMessage(pattern='/logs'))
        async def remove_schedule(event):
            await self._check_allowed_chat(event)
            parts = event.text.split()
            num = int(parts[1]) if len(parts) > 1 else 50
            logs = "\n".join(get_recent_logs(num))[-4096:]
            await event.respond(logs)

        @self.client.on(events.NewMessage(pattern='/weather'))
        async def current_weather(event):
            await self._check_allowed_chat(event)
            weather = await self.weather_descriptor.get_forecast()
            await event.respond(f"```{str(weather)}````")

    async def _setup_menu(self):
        commands = [
            ('start', 'Start bot'),
            ('help', 'Show help message'),
            ('settings', 'Show current settings'),
            ('set_variable', 'Set config variable'),
            ('delete_variable', 'Delete config variable'),
            ('update', 'Force avatar update now'),
            ('schedule', 'Show update schedule'),
            ('add_time', 'Add new update time (HH:MM)'),
            ('delete_time', 'Delete update time (HH:MM)'),
            ('logs', 'Show recent logs'),
            ('settings', 'Show current settings in copy-friendly format')
        ]
        await self.client(telethon.tl.functions.bots.SetBotCommandsRequest(
            scope=telethon.tl.types.BotCommandScopeDefault(),
            lang_code='en',
            commands=[telethon.tl.types.BotCommand(*cmd) for cmd in commands]
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
/help - Show this message"""
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
        if self._config.previous_prompt_text == self._config.prompt_text:
            message = "prompt hasn't changed, no update needed"
            logger.info(message)
            return message
        try:
            self._is_job_running = True
            await self.updater.async_update_avatar()
            used_prompt = self.avatar_generator.prepare_prompt()
            self._config['previous_prompt_text'] = used_prompt
            logger.info(f"used prompt {used_prompt}")
            return "✅ Avatar updated!"
        except Exception as e:
            error = f"error while updating avatar: {str(e)}"
            logger.exception(e)
            return error
        finally:
            self._is_job_running = False


    def _load_and_start_schedule(self):
        schedule = self._config.load_schedule()
        self.scheduler.remove_all_jobs()
        for time_str in schedule:
            hour, minute = map(int, time_str.split(':'))
            self.scheduler.add_job(
                self._update_avatar,
                'cron',
                hour=hour,
                minute=minute,
                timezone='UTC',
                max_instances=1
            )
        if schedule and self.scheduler.state == 0:
            self.scheduler.start()

    def _restart_scheduler(self):
        self._load_and_start_schedule()
