from typing import ClassVar

from tuican.components import Button, ScreenGroup

from dava.screens.base import DavaScreen
from dava.service import DavaService


class VideoActionsMainScreen(DavaScreen):
    """Main screen for managing video actions: choose weather or holiday list."""

    description: ClassVar[str] = "Video Actions"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.back_btn = Button("« Back", on_change=self.go_back)
        self.weather_btn = Button("🌦️ Weather actions", on_change=self.open_weather_list)
        self.holiday_btn = Button("🎉 Holiday actions", on_change=self.open_holiday_list)
        self.add_weather_btn = Button("➕ Add weather action", on_change=self.open_add_weather)
        self.add_holiday_btn = Button("➕ Add holiday action", on_change=self.open_add_holiday)

        super().__init__(group, service, message="**🎥 Video Actions**\n\nManage triggers for video avatar generation:")
        for btn in (self.back_btn, self.weather_btn, self.holiday_btn,
                    self.add_weather_btn, self.add_holiday_btn):
            self.add_component(btn)

    def get_layout(self):
        return [
            [self.weather_btn],
            [self.holiday_btn],
            [self.add_weather_btn],
            [self.add_holiday_btn],
            [self.back_btn],
        ]

    async def open_weather_list(self):
        from dava.screens.action_paginator_screen import ActionPaginatorScreen
        await self.go_to_screen(ActionPaginatorScreen(self.group, self.service, "weather"))

    async def open_holiday_list(self):
        from dava.screens.action_paginator_screen import ActionPaginatorScreen
        await self.go_to_screen(ActionPaginatorScreen(self.group, self.service, "holidays"))

    async def open_add_weather(self):
        from dava.screens.action_add_screen import ActionAddScreen
        await self.go_to_screen(ActionAddScreen(self.group, self.service, "weather"))

    async def open_add_holiday(self):
        from dava.screens.action_add_screen import ActionAddScreen
        await self.go_to_screen(ActionAddScreen(self.group, self.service, "holidays"))
