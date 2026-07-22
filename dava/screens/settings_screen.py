from typing import ClassVar

from tuican.components import Button, ScreenGroup

from dava.config import ADMIN_SETTING_CATEGORIES, USER_SETTING_CATEGORIES
from dava.screens.base import DavaScreen
from dava.service import DavaService


class SettingsScreen(DavaScreen):
    description: ClassVar[str] = "Settings"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.close_btn = Button("❌ Close", on_change=self.close_settings)
        self.refresh_btn = Button("🔄 Refresh", on_change=self.refresh_settings)
        self.schedule_btn = Button("📅 Schedule", on_change=self.open_schedule)
        self.admin_btn = Button("👑 Admin / Globals", on_change=self.open_admin)

        # Category buttons will be created dynamically
        self._category_buttons: list[Button] = []

        super().__init__(group, service)
        self._build_category_buttons()

    def _build_category_buttons(self):
        self._category_buttons = []
        for cat_name in USER_SETTING_CATEGORIES.keys():
            btn = Button(cat_name, on_change=self._make_open_category(cat_name))
            self._category_buttons.append(btn)
            self.add_component(btn)

    def _make_open_category(self, cat_name: str):
        async def handler():
            from dava.screens.category_screen import CategoryScreen
            await self.go_to_screen(CategoryScreen(self.group, self.service, cat_name))
        return handler

    def get_layout(self):
        rows: list = []
        # Category buttons in pairs
        row = []
        for btn in self._category_buttons:
            row.append(btn)
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)

        rows.append([self.schedule_btn])
        if self.is_admin():
            rows.append([self.admin_btn])
        rows.append([self.refresh_btn, self.close_btn])
        return rows

    @property
    def message(self) -> str | None:
        # Recompute summary each time message is accessed
        return self.service.build_settings_summary(self.current_user_id())

    async def close_settings(self):
        await self.go_home()

    async def refresh_settings(self):
        # Just re-display to refresh the summary
        update = self.update
        if update is not None:
            await self.display(update)

    async def open_schedule(self):
        from dava.screens.schedule_screen import ScheduleScreen
        await self.go_to_screen(ScheduleScreen(self.group, self.service))

    async def open_admin(self):
        from dava.screens.admin_globals_screen import AdminGlobalsScreen
        await self.go_to_screen(AdminGlobalsScreen(self.group, self.service))
