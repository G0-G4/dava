import logging
from typing import ClassVar

from tuican import Application
from tuican.components import Screen, ScreenGroup
from tuican.update import TuicanUpdate, get_user_id

from dava.config import Config
from dava.service import DavaService
from dava.screens.main_screen import MainScreen
from dava.screens.settings_screen import SettingsScreen
from dava.screens.schedule_screen import ScheduleScreen
from dava.screens.admin_globals_screen import AdminGlobalsScreen
from dava.screens.edit_screen import EditScreen
from dava.screens.action_screen import AddActionScreen, DeleteActionScreen
from dava.screens.users_screen import GrantUserScreen, RevokeUserScreen, UsersScreen
from dava.screens.simple_screens import (
    UpdateScreen,
    WeatherScreen,
    LogsScreen,
    ConnectionScreen,
    HelpScreen,
    UploadScreen,
    UploadReferenceScreen,
    GenerateReferenceScreen,
    ClearReferenceScreen,
    SetVariableScreen,
    DeleteVariableScreen,
    SetGlobalVariableScreen,
    DeleteGlobalVariableScreen,
    VideoModeScreen,
    SetActionScreen,
    DeleteActionScreen,
)

logger = logging.getLogger(__name__)


class DavaScreenGroup(ScreenGroup):
    description: ClassVar[str] = "dava"

    def __init__(self, service: DavaService, home_screen_cls):
        self._service = service
        home = home_screen_cls(self, service)
        super().__init__(home)

    async def on_start(self, update: TuicanUpdate) -> None:
        # Delegate on_start to the top screen so it can initialize before display
        await self._screen_stack[-1].on_start(update)


def create_screen_factories(service: DavaService) -> dict[str, type[Screen]]:
    def make_group(home_cls):
        def factory():
            return DavaScreenGroup(service, home_cls)
        return factory

    return {
        "start": make_group(MainScreen),
        "help": make_group(MainScreen),
        "settings": make_group(SettingsScreen),
        "update": make_group(UpdateScreen),
        "upload": make_group(UploadScreen),
        "upload_reference": make_group(UploadReferenceScreen),
        "generate_reference": make_group(GenerateReferenceScreen),
        "clear_reference": make_group(ClearReferenceScreen),
        "schedule": make_group(ScheduleScreen),
        "add_time": make_group(ScheduleScreen),
        "delete_time": make_group(ScheduleScreen),
        "weather": make_group(WeatherScreen),
        "video_mode": make_group(VideoModeScreen),
        "set_action": make_group(SetActionScreen),
        "delete_action": make_group(DeleteActionScreen),
        "connection": make_group(ConnectionScreen),
        "grant": make_group(GrantUserScreen),
        "revoke": make_group(RevokeUserScreen),
        "list_users": make_group(UsersScreen),
        "users": make_group(UsersScreen),
        "logs": make_group(LogsScreen),
        "set_variable": make_group(SetVariableScreen),
        "delete_variable": make_group(DeleteVariableScreen),
        "set_global_variable": make_group(AdminGlobalsScreen),
        "delete_global_variable": make_group(DeleteGlobalVariableScreen),
    }


def create_app(
    config: Config,
    service: DavaService,
    client,
) -> Application:
    screens = create_screen_factories(service)

    app = Application(
        config.bot_token,
        screens,
        transport="telethon",
        api_id=config.api_id,
        api_hash=config.api_hash,
    )

    # Override the transport with our custom one that wraps the existing client
    from dava.transport import DavaTelethonTransport
    app._transport = DavaTelethonTransport(client, config.bot_token, config.api_id, config.api_hash)

    @app.middleware
    async def check_allowed(update: TuicanUpdate) -> bool:
        user_id = get_user_id(update)
        if not service.db.is_allowed(user_id):
            await app.backend.send_notification(
                update,
                "⛔ Access not granted. Please contact the admin to get access."
            )
            return False
        return True

    return app
