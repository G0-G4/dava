from typing import ClassVar

from tuican.components import Button, Input, ScreenGroup

from dava.screens.base import DavaScreen
from dava.service import DavaService


class ScheduleScreen(DavaScreen):
    description: ClassVar[str] = "Schedule"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.back_btn = Button("« Back", on_change=self.go_back)

        # Delete buttons built dynamically
        self._delete_buttons: list[Button] = []

        self.time_input = Input[str](
            text="➕ Add time (HH:MM UTC)",
            validation_function=lambda x: x,
            on_change=self.save_time,
            active_prompt="Enter time (HH:MM UTC): ",
        )

        super().__init__(group, service)
        self.add_component(self.back_btn)
        self.add_component(self.time_input)

    def _build_delete_buttons(self):
        # Remove old buttons from registry
        for btn in self._delete_buttons:
            self.delete_component(btn)
        self._delete_buttons = []

        user_id = self.current_user_id()
        schedule = self.service.db.load_schedule(user_id)
        for time_str in schedule:
            btn = Button(f"🗑 {time_str}", on_change=self._make_delete_time(time_str))
            self._delete_buttons.append(btn)
            self.add_component(btn)

    def _make_delete_time(self, time_str: str):
        async def handler():
            user_id = self.current_user_id()
            schedule = self.service.db.load_schedule(user_id)
            if time_str in schedule:
                schedule.remove(time_str)
                self.service.db.save_schedule(user_id, schedule)
                self.service.restart_scheduler(user_id)
                self._build_delete_buttons()
                await self.display(self.update)
        return handler

    async def save_time(self):
        time_str = self.time_input.value
        if time_str is None:
            return
        time_str = time_str.strip()
        if not self.service.validate_time(time_str):
            self.time_input.value = None
            return
        user_id = self.current_user_id()
        schedule = self.service.db.load_schedule(user_id)
        if time_str not in schedule:
            schedule.append(time_str)
            self.service.db.save_schedule(user_id, schedule)
            self.service.restart_scheduler(user_id)
            self.time_input.value = None
            self._build_delete_buttons()
            await self.display(self.update)
        else:
            self.time_input.value = None

    def get_layout(self):
        self._build_delete_buttons()
        rows: list = []
        for btn in self._delete_buttons:
            rows.append([btn])
        rows.append([self.time_input])
        rows.append([self.back_btn])
        return rows

    @property
    def message(self) -> str | None:
        user_id = self.current_user_id()
        schedule = self.service.db.load_schedule(user_id)
        text = "**📅 Your update schedule** (UTC times)\n"
        if schedule:
            text += "Current: " + ", ".join(schedule)
        else:
            text += "No times set."
        return text
