import shlex
from typing import ClassVar

from tuican.components import Button, Input, ScreenGroup
from tuican.update import TuicanUpdate

from dava.screens.base import DavaScreen
from dava.service import DavaService


class AddActionScreen(DavaScreen):
    description: ClassVar[str] = "Add Action"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.input_field = Input[str](
            text="Action",
            validation_function=lambda x: x,
            on_change=self.save_action,
            active_prompt="Enter action (e.g. weather 95 lightning flash): ",
        )
        self.cancel_btn = Button("❌ Cancel", on_change=self.go_back)

        super().__init__(
            group,
            service,
            message="➕ Adding a video action.\n\n"
                    "Send in this format:\n"
                    "weather <code> <action text>\n"
                    "holiday \"name with spaces\" <action text>\n\n"
                    "Examples:\n"
                    "weather 95 lightning flash, user flinches\n"
                    "holiday \"New Year's Day\" fireworks, user cheers",
        )
        self.add_component(self.input_field)
        self.add_component(self.cancel_btn)

    def get_layout(self):
        return [
            [self.input_field],
            [self.cancel_btn],
        ]

    async def display(self, update: TuicanUpdate) -> None:
        await super().display(update)
        await self.set_focus(self.input_field)

    async def save_action(self):
        text = self.input_field.value
        if text is None:
            return
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()
        if len(parts) < 3 or parts[0] not in ("weather", "holiday"):
            await self.backend.send_plain_message(
                self.update,
                "❌ Invalid format.\n"
                "Send e.g.:\n"
                "weather 95 lightning flash, user flinches\n"
                "holiday \"New Year's Day\" fireworks exploding"
            )
            return
        action_type = parts[0]
        key = parts[1]
        action_text = " ".join(parts[2:])
        user_id = self.current_user_id()
        result = self.service.apply_video_action(user_id, action_type, key, action_text)
        await self.backend.send_plain_message(self.update, result)
        await self.go_back()


class DeleteActionScreen(DavaScreen):
    description: ClassVar[str] = "Delete Action"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.input_field = Input[str](
            text="Action to delete",
            validation_function=lambda x: x,
            on_change=self.delete_action,
            active_prompt="Enter action to delete (e.g. weather 95): ",
        )
        self.cancel_btn = Button("❌ Cancel", on_change=self.go_back)

        super().__init__(
            group,
            service,
            message="🗑 Deleting a video action.\n\n"
                    "Send in this format:\n"
                    "weather <code>\n"
                    "holiday \"name with spaces\"\n\n"
                    "Example: weather 95",
        )
        self.add_component(self.input_field)
        self.add_component(self.cancel_btn)

    def get_layout(self):
        return [
            [self.input_field],
            [self.cancel_btn],
        ]

    async def display(self, update: TuicanUpdate) -> None:
        await super().display(update)
        await self.set_focus(self.input_field)

    async def delete_action(self):
        text = self.input_field.value
        if text is None:
            return
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()
        if len(parts) < 2 or parts[0] not in ("weather", "holiday"):
            await self.backend.send_plain_message(
                self.update,
                "❌ Invalid format.\n"
                "Send e.g.:\n"
                "weather 95\n"
                "holiday \"New Year's Day\""
            )
            return
        action_type = parts[0]
        key = parts[1]
        user_id = self.current_user_id()
        result = self.service.delete_video_action(user_id, action_type, key)
        await self.backend.send_plain_message(self.update, result)
        await self.go_back()
