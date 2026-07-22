from typing import ClassVar

from tuican.components import Button, Input, ScreenGroup
from tuican.update import TuicanUpdate, get_user_id

from dava.screens.base import DavaScreen
from dava.service import DavaService


class EditScreen(DavaScreen):
    description: ClassVar[str] = "Edit"

    def __init__(self, group: ScreenGroup, service: DavaService, key: str, is_global: bool = False):
        self.key = key
        self.is_global = is_global

        self.input_field = Input[str](
            text=f"New {key}",
            validation_function=lambda x: x,
            on_change=self.save_value,
            active_prompt=f"Enter new {key}: ",
        )
        self.cancel_btn = Button("❌ Cancel", on_change=self.go_back)

        super().__init__(group, service)
        self.add_component(self.input_field)
        self.add_component(self.cancel_btn)

    def get_layout(self):
        return [
            [self.input_field],
            [self.cancel_btn],
        ]

    async def display(self, update: TuicanUpdate) -> None:
        user_id = get_user_id(update)
        if self.is_global:
            current_value = str(self.service.get_admin_value(self.key) or "")
        else:
            current_value = self.service.get_effective_display(user_id, self.key, truncate=200)
        self.message = f"✏️ Editing **{self.key}**\nCurrent value:\n```\n{current_value}\n```\n\nSend the new value. Type /cancel to abort."
        await self.display_with_focus(update, self.input_field)

    async def save_value(self):
        user_id = self.current_user_id()
        new_value = self.input_field.value
        if new_value is None:
            return

        if self.is_global:
            from dava.config import convert_value
            converted = convert_value(self.key, new_value)
            self.service.db.set_global_default(self.key, converted)
        else:
            self.service.db.save_user_config(user_id, self.key, new_value)
            if self.key in ("place", "latitude", "longitude"):
                await self.backend.send_plain_message(
                    self.update,
                    "📍 Location updated. To stabilize backgrounds for this place, run /generate_reference or /upload_reference."
                )

        await self.go_back()
