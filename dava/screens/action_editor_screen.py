from typing import ClassVar

from tuican.components import Button, Input, ScreenGroup
from tuican.update import TuicanUpdate

from dava.screens.base import DavaScreen
from dava.service import DavaService


class ActionEditorScreen(DavaScreen):
    """Screen to edit or delete a single video action."""

    description: ClassVar[str] = "Edit Action"

    def __init__(
        self,
        group: ScreenGroup,
        service: DavaService,
        category: str,
        key: str,
        value: str,
    ):
        self.category = category
        self.key = key

        self.back_btn = Button("« Back to list", on_change=self.go_back)
        self.delete_btn = Button("🗑 Delete", on_change=self.do_delete)

        self.value_input = Input[str](
            text="Action text",
            validation_function=lambda x: x,
            on_change=self.save_value,
            active_prompt="Enter action description: ",
        )
        self.value_input.value = value

        super().__init__(group, service, message=f"**Edit {category} action**\n\nKey: `{key}`")
        self.add_component(self.back_btn)
        self.add_component(self.delete_btn)
        self.add_component(self.value_input)

    def get_layout(self):
        return [
            [self.value_input],
            [self.delete_btn],
            [self.back_btn],
        ]

    async def display(self, update: TuicanUpdate) -> None:
        await super().display(update)
        await self.set_focus(self.value_input)

    async def save_value(self):
        new_value = self.value_input.value
        if new_value is None:
            return
        user_id = self.current_user_id()
        result = self.service.apply_video_action(
            user_id, self.category, self.key, new_value
        )
        if result.startswith("✅"):
            await self.backend.send_plain_message(self.update, "✅ Saved")
        else:
            await self.backend.send_plain_message(self.update, result)
        await self.go_back()

    async def do_delete(self):
        user_id = self.current_user_id()
        result = self.service.delete_video_action(user_id, self.category, self.key)
        if result.startswith("✅"):
            await self.backend.send_plain_message(self.update, "🗑 Deleted")
        else:
            await self.backend.send_plain_message(self.update, result)
        await self.go_back()
