from typing import ClassVar

from tuican.components import Button, Input, ScreenGroup
from tuican.update import TuicanUpdate

from dava.screens.base import DavaScreen
from dava.service import DavaService


class ActionAddScreen(DavaScreen):
    """Screen to add a new video action (weather code or holiday name + description)."""

    description: ClassVar[str] = "Add Action"

    def __init__(
        self,
        group: ScreenGroup,
        service: DavaService,
        category: str,  # "weather" or "holiday"
    ):
        self.category = category
        self.back_btn = Button("« Back", on_change=self.go_back)

        key_label = "Weather code (e.g. 95)" if category == "weather" else 'Holiday name (e.g. "New Year")'
        self.key_input = Input[str](
            text=key_label,
            validation_function=lambda x: x,
            on_change=self.on_key_entered,
            active_prompt="Enter key: ",
        )
        self.value_input = Input[str](
            text="Action description",
            validation_function=lambda x: x,
            on_change=self.do_save,
            active_prompt="Enter description: ",
        )

        super().__init__(group, service, message=f"**➕ Add {category} action**")
        self.add_component(self.back_btn)
        self.add_component(self.key_input)
        self.add_component(self.value_input)

    def get_layout(self):
        return [
            [self.key_input],
            [self.value_input],
            [self.back_btn],
        ]

    async def display(self, update: TuicanUpdate) -> None:
        await super().display(update)
        await self.set_focus(self.key_input)

    async def on_key_entered(self):
        # on_change fires only after a committed message; None means not submitted
        key = self.key_input.value
        if key is None:
            return
        if not key.strip():
            await self.backend.send_plain_message(self.update, "❌ Key cannot be empty")
            return
        # Move focus so description input accepts the next message
        await self.set_focus(self.value_input)

    async def do_save(self):
        key = self.key_input.value
        value = self.value_input.value
        if key is None or not key.strip() or value is None:
            return
        if not value.strip():
            await self.backend.send_plain_message(
                self.update, "❌ Action description cannot be empty"
            )
            return
        user_id = self.current_user_id()
        result = self.service.apply_video_action(
            user_id, self.category, key.strip(), value.strip()
        )
        if result.startswith("✅"):
            await self.backend.send_plain_message(self.update, f"✅ Added {self.category}/{key}")
        else:
            await self.backend.send_plain_message(self.update, result)
        await self.go_back()
