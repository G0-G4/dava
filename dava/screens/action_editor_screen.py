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
        self.current_value = value

        self.back_btn = Button("« Back to list", on_change=self.go_back)
        self.delete_btn = Button("🗑 Delete", on_change=self.do_delete)

        self.value_input = Input[str](
            text="Action text",
            validation_function=lambda x: x,
            on_change=self.save_value,
            active_prompt="Enter action description: ",
        )
        self.value_input.value = value

        super().__init__(group, service)
        self.add_component(self.back_btn)
        self.add_component(self.delete_btn)
        self.add_component(self.value_input)

    def get_layout(self):
        return [
            [self.value_input],
            [self.delete_btn],
            [self.back_btn],
        ]

    def _build_message(self) -> str:
        label = "weather" if self.category == "weather" else "holiday"
        return (
            f"**Edit {label} action**\n"
            f"Key: `{self.key}`\n\n"
            f"Current description (copy, edit, send):\n"
            f"```\n{self.current_value}\n```\n\n"
            f"Send the new description below."
        )

    async def display(self, update: TuicanUpdate) -> None:
        self.message = self._build_message()
        await self.display_with_focus(update, self.value_input)

    async def save_value(self):
        # on_change fires only after a committed message; None means not submitted
        new_value = self.value_input.value
        if new_value is None:
            return
        if not str(new_value).strip():
            await self.backend.send_plain_message(
                self.update, "❌ Action description cannot be empty"
            )
            return
        user_id = self.current_user_id()
        result = self.service.apply_video_action(
            user_id, self.category, self.key, str(new_value).strip()
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
