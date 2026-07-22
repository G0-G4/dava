from typing import ClassVar

from tuican.components import Button, ScreenGroup

from dava.screens.base import DavaScreen
from dava.service import DavaService


class MainScreen(DavaScreen):
    description: ClassVar[str] = "Main menu"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.settings_btn = Button("⚙️ Settings", on_change=self.open_settings)
        self.update_btn = Button("🔄 Update", on_change=self.open_update)
        self.weather_btn = Button("🌦️ Weather", on_change=self.open_weather)
        self.upload_btn = Button("📸 Upload", on_change=self.open_upload)
        self.schedule_btn = Button("📅 Schedule", on_change=self.open_schedule)
        self.connection_btn = Button("🔗 Connection", on_change=self.open_connection)
        self.help_btn = Button("❓ Help", on_change=self.open_help)

        # Admin buttons (conditionally rendered)
        self.logs_btn = Button("📋 Logs", on_change=self.open_logs)
        self.users_btn = Button("👥 Users", on_change=self.open_users)
        self.grant_btn = Button("✅ Grant", on_change=self.open_grant)
        self.revoke_btn = Button("❌ Revoke", on_change=self.open_revoke)

        super().__init__(group, service, message="🤖 Dynamic Avatar Bot\nChoose an action:")

    def get_layout(self):
        rows = [
            [self.settings_btn, self.update_btn],
            [self.weather_btn, self.upload_btn],
            [self.schedule_btn, self.connection_btn],
            [self.help_btn],
        ]
        if self.is_admin():
            rows.append([self.logs_btn, self.users_btn])
            rows.append([self.grant_btn, self.revoke_btn])
        return rows

    async def open_settings(self):
        from dava.screens.settings_screen import SettingsScreen
        await self.go_to_screen(SettingsScreen(self.group, self.service))

    async def open_update(self):
        from dava.screens.simple_screens import UpdateScreen
        await self.go_to_screen(UpdateScreen(self.group, self.service))

    async def open_weather(self):
        from dava.screens.simple_screens import WeatherScreen
        await self.go_to_screen(WeatherScreen(self.group, self.service))

    async def open_upload(self):
        from dava.screens.simple_screens import UploadScreen
        await self.go_to_screen(UploadScreen(self.group, self.service))

    async def open_schedule(self):
        from dava.screens.schedule_screen import ScheduleScreen
        await self.go_to_screen(ScheduleScreen(self.group, self.service))

    async def open_connection(self):
        from dava.screens.simple_screens import ConnectionScreen
        await self.go_to_screen(ConnectionScreen(self.group, self.service))

    async def open_help(self):
        from dava.screens.simple_screens import HelpScreen
        await self.go_to_screen(HelpScreen(self.group, self.service))

    async def open_logs(self):
        from dava.screens.simple_screens import LogsScreen
        await self.go_to_screen(LogsScreen(self.group, self.service))

    async def open_users(self):
        from dava.screens.simple_screens import UsersScreen
        await self.go_to_screen(UsersScreen(self.group, self.service))

    async def open_grant(self):
        from dava.screens.simple_screens import GrantScreen
        await self.go_to_screen(GrantScreen(self.group, self.service))

    async def open_revoke(self):
        from dava.screens.simple_screens import RevokeScreen
        await self.go_to_screen(RevokeScreen(self.group, self.service))
