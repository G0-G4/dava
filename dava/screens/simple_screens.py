import json
import shlex
from typing import ClassVar

from tuican.components import Button, Input, ScreenGroup
from tuican.update import TuicanUpdate

from dava.config import (
    ALL_CONFIGURABLE_KEYS,
    USER_CONFIGURABLE_KEYS,
)
from dava.screens.base import DavaScreen
from dava.service import DavaService


class OneShotScreen(DavaScreen):
    """Base for screens that perform an action and show a result with a back button."""

    description: ClassVar[str] = "One-shot"

    def __init__(self, group: ScreenGroup, service: DavaService, message: str | None = None):
        self.back_btn = Button("« Back to menu", on_change=self.go_home)
        super().__init__(group, service, message=message)
        self.add_component(self.back_btn)

    def get_layout(self):
        return [[self.back_btn]]


class UpdateScreen(OneShotScreen):
    description: ClassVar[str] = "Update avatar"

    def __init__(self, group: ScreenGroup, service: DavaService):
        super().__init__(group, service)

    async def display(self, update: TuicanUpdate) -> None:
        user_id = update.user_id or 0
        result = await self.service.update_avatar(user_id)
        self.message = result
        await super().display(update)


class WeatherScreen(OneShotScreen):
    description: ClassVar[str] = "Weather"

    def __init__(self, group: ScreenGroup, service: DavaService):
        super().__init__(group, service)

    async def display(self, update: TuicanUpdate) -> None:
        user_id = update.user_id or 0
        self.message = self.service.get_weather_text(user_id)
        await super().display(update)


class LogsScreen(OneShotScreen):
    description: ClassVar[str] = "Logs"

    def __init__(self, group: ScreenGroup, service: DavaService):
        super().__init__(group, service)

    async def display(self, update: TuicanUpdate) -> None:
        if not self.service.is_admin(update.user_id or 0):
            self.message = "⛔ This command is for admins only."
            await super().display(update)
            return
        parts = update.message_text.split() if update.message_text else []
        num = int(parts[1]) if len(parts) > 1 else 50
        self.message = self.service.get_logs(num)
        await super().display(update)


class ConnectionScreen(OneShotScreen):
    description: ClassVar[str] = "Connection"

    def __init__(self, group: ScreenGroup, service: DavaService):
        super().__init__(group, service)

    async def display(self, update: TuicanUpdate) -> None:
        user_id = update.user_id or 0
        self.message = self.service.get_connection_text(user_id)
        await super().display(update)


class UsersScreen(OneShotScreen):
    description: ClassVar[str] = "Users"

    def __init__(self, group: ScreenGroup, service: DavaService):
        super().__init__(group, service)

    async def display(self, update: TuicanUpdate) -> None:
        if not self.service.is_admin(update.user_id or 0):
            self.message = "⛔ This command is for admins only."
            await super().display(update)
            return
        self.message = self.service.get_users_text()
        await super().display(update)


class HelpScreen(OneShotScreen):
    description: ClassVar[str] = "Help"

    def __init__(self, group: ScreenGroup, service: DavaService):
        super().__init__(group, service)

    async def display(self, update: TuicanUpdate) -> None:
        self.message = self.service.get_help_text()
        await super().display(update)


class UploadScreen(OneShotScreen):
    description: ClassVar[str] = "Upload"

    def __init__(self, group: ScreenGroup, service: DavaService):
        super().__init__(group, service)

    async def display(self, update: TuicanUpdate) -> None:
        self.message = (
            "📸 Please send your base image (photo).\n\n"
            "The bot will use it as the identity source for avatar generation."
        )
        await super().display(update)


class UploadReferenceScreen(OneShotScreen):
    description: ClassVar[str] = "Upload Reference"

    def __init__(self, group: ScreenGroup, service: DavaService):
        super().__init__(group, service)

    async def display(self, update: TuicanUpdate) -> None:
        self.message = (
            "🖼️ Please send a full scene reference photo (ideally you + the desired background/place).\n"
            "This will be used as a visual prior for stable backgrounds in future generations.\n"
            "/generate_reference is recommended (it uses neutral clear conditions)."
        )
        await super().display(update)


class GenerateReferenceScreen(OneShotScreen):
    description: ClassVar[str] = "Generate Reference"

    def __init__(self, group: ScreenGroup, service: DavaService):
        super().__init__(group, service)

    async def display(self, update: TuicanUpdate) -> None:
        user_id = update.user_id or 0
        try:
            ref_path = await self.service.generate_and_save_reference(user_id)
            self.message = (
                f"✅ Scene reference generated and activated.\n"
                f"Saved to: {ref_path}\n\n"
                "Future /update runs will use it for consistent backgrounds."
            )
        except Exception as e:
            self.message = f"❌ Failed to generate reference: {e}"
        await super().display(update)


class ClearReferenceScreen(OneShotScreen):
    description: ClassVar[str] = "Clear Reference"

    def __init__(self, group: ScreenGroup, service: DavaService):
        super().__init__(group, service)

    async def display(self, update: TuicanUpdate) -> None:
        user_id = update.user_id or 0
        self.service.db.clear_reference_image(user_id)
        self.message = "✅ Scene reference cleared. Future updates will use your base image + full prompt again."
        await super().display(update)


class GrantScreen(DavaScreen):
    description: ClassVar[str] = "Grant"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.user_input = Input[str](
            text="User ID",
            validation_function=lambda x: x,
            on_change=self.do_grant,
            active_prompt="Enter user ID to grant: ",
        )
        self.cancel_btn = Button("❌ Cancel", on_change=self.go_home)
        super().__init__(group, service, message="✅ Grant access to user\nEnter the user ID:")
        self.add_component(self.user_input)
        self.add_component(self.cancel_btn)

    def get_layout(self):
        return [[self.user_input], [self.cancel_btn]]

    async def display(self, update: TuicanUpdate) -> None:
        if not self.service.is_admin(update.user_id or 0):
            await self.backend.send_plain_message(update, "⛔ This command is for admins only.")
            return
        await super().display(update)
        await self.set_focus(self.user_input)

    async def do_grant(self):
        user_id_str = self.user_input.value
        if user_id_str is None:
            return
        try:
            target_user_id = int(user_id_str)
        except ValueError:
            await self.backend.send_plain_message(self.update, "❌ Invalid user ID")
            return
        self.service.db.grant(target_user_id)
        self.service.restore_user_schedule(target_user_id)
        await self.backend.send_plain_message(self.update, f"✅ Granted access to user {target_user_id}")
        await self.go_home()

    async def on_command(self, args, update):
        if not self.service.is_admin(update.user_id or 0):
            await self.backend.send_plain_message(update, "⛔ This command is for admins only.")
            return
        if len(args) >= 1:
            try:
                target_user_id = int(args[0])
            except ValueError:
                await self.backend.send_plain_message(update, "❌ Invalid user ID")
                return
            self.service.db.grant(target_user_id)
            self.service.restore_user_schedule(target_user_id)
            await self.backend.send_plain_message(update, f"✅ Granted access to user {target_user_id}")
            await self.go_home()
        else:
            await self.on_start(update)


class RevokeScreen(DavaScreen):
    description: ClassVar[str] = "Revoke"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.user_input = Input[str](
            text="User ID",
            validation_function=lambda x: x,
            on_change=self.do_revoke,
            active_prompt="Enter user ID to revoke: ",
        )
        self.cancel_btn = Button("❌ Cancel", on_change=self.go_home)
        super().__init__(group, service, message="❌ Revoke access from user\nEnter the user ID:")
        self.add_component(self.user_input)
        self.add_component(self.cancel_btn)

    def get_layout(self):
        return [[self.user_input], [self.cancel_btn]]

    async def display(self, update: TuicanUpdate) -> None:
        if not self.service.is_admin(update.user_id or 0):
            await self.backend.send_plain_message(update, "⛔ This command is for admins only.")
            return
        await super().display(update)
        await self.set_focus(self.user_input)

    async def do_revoke(self):
        user_id_str = self.user_input.value
        if user_id_str is None:
            return
        try:
            target_user_id = int(user_id_str)
        except ValueError:
            await self.backend.send_plain_message(self.update, "❌ Invalid user ID")
            return
        self.service.db.revoke(target_user_id)
        self.service.remove_user_schedule(target_user_id)
        await self.backend.send_plain_message(self.update, f"✅ Revoked access from user {target_user_id}")
        await self.go_home()

    async def on_command(self, args, update):
        if not self.service.is_admin(update.user_id or 0):
            await self.backend.send_plain_message(update, "⛔ This command is for admins only.")
            return
        if len(args) >= 1:
            try:
                target_user_id = int(args[0])
            except ValueError:
                await self.backend.send_plain_message(update, "❌ Invalid user ID")
                return
            self.service.db.revoke(target_user_id)
            self.service.remove_user_schedule(target_user_id)
            await self.backend.send_plain_message(update, f"✅ Revoked access from user {target_user_id}")
            await self.go_home()
        else:
            await self.on_start(update)


class SetVariableScreen(DavaScreen):
    description: ClassVar[str] = "Set Variable"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.key_input = Input[str](
            text="Variable name",
            validation_function=lambda x: x,
            on_change=self.on_key_entered,
            active_prompt="Enter variable name: ",
        )
        self.value_input = Input[str](
            text="Value",
            validation_function=lambda x: x,
            on_change=self.do_set,
            active_prompt="Enter value: ",
        )
        self.cancel_btn = Button("❌ Cancel", on_change=self.go_home)
        super().__init__(group, service, message="Set a user variable")
        self.add_component(self.key_input)
        self.add_component(self.value_input)
        self.add_component(self.cancel_btn)
        self._pending_key: str | None = None

    def get_layout(self):
        return [
            [self.key_input],
            [self.value_input],
            [self.cancel_btn],
        ]

    async def display(self, update: TuicanUpdate) -> None:
        await super().display(update)
        await self.set_focus(self.key_input)

    async def on_key_entered(self):
        key = self.key_input.value
        if key is None or key not in USER_CONFIGURABLE_KEYS:
            await self.backend.send_plain_message(
                self.update,
                f"❌ `{key}` is not a user-configurable variable."
            )
            return
        self._pending_key = key
        await self.set_focus(self.value_input)

    async def do_set(self):
        key = self._pending_key
        value = self.value_input.value
        if key is None or value is None:
            return
        user_id = self.current_user_id()
        self.service.db.save_user_config(user_id, key, value)
        await self.backend.send_plain_message(self.update, f"✅ {key} set to {value}")
        await self.go_home()

    async def on_command(self, args, update):
        if len(args) >= 2:
            name = args[0]
            val = args[1]
            if name not in USER_CONFIGURABLE_KEYS:
                await self.backend.send_plain_message(
                    update,
                    f"❌ `{name}` is not a user-configurable variable."
                )
                return
            user_id = update.user_id or 0
            self.service.db.save_user_config(user_id, name, val)
            await self.backend.send_plain_message(update, f"✅ {name} set to {val}")
            await self.go_home()
        else:
            await self.on_start(update)


class DeleteVariableScreen(DavaScreen):
    description: ClassVar[str] = "Delete Variable"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.key_input = Input[str](
            text="Variable name",
            validation_function=lambda x: x,
            on_change=self.do_delete,
            active_prompt="Enter variable name to delete: ",
        )
        self.cancel_btn = Button("❌ Cancel", on_change=self.go_home)
        super().__init__(group, service, message="Delete a user variable")
        self.add_component(self.key_input)
        self.add_component(self.cancel_btn)

    def get_layout(self):
        return [[self.key_input], [self.cancel_btn]]

    async def display(self, update: TuicanUpdate) -> None:
        await super().display(update)
        await self.set_focus(self.key_input)

    async def do_delete(self):
        key = self.key_input.value
        if key is None:
            return
        user_id = self.current_user_id()
        self.service.db.delete_user_config_key(user_id, key)
        await self.backend.send_plain_message(self.update, f"✅ {key} has been deleted")
        await self.go_home()

    async def on_command(self, args, update):
        if len(args) >= 1:
            name = args[0]
            user_id = update.user_id or 0
            self.service.db.delete_user_config_key(user_id, name)
            await self.backend.send_plain_message(update, f"✅ {name} has been deleted")
            await self.go_home()
        else:
            await self.on_start(update)


class SetGlobalVariableScreen(DavaScreen):
    description: ClassVar[str] = "Set Global Variable"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.key_input = Input[str](
            text="Variable name",
            validation_function=lambda x: x,
            on_change=self.on_key_entered,
            active_prompt="Enter global variable name: ",
        )
        self.value_input = Input[str](
            text="Value",
            validation_function=lambda x: x,
            on_change=self.do_set,
            active_prompt="Enter global value: ",
        )
        self.cancel_btn = Button("❌ Cancel", on_change=self.go_home)
        super().__init__(group, service, message="Set a global default")
        self.add_component(self.key_input)
        self.add_component(self.value_input)
        self.add_component(self.cancel_btn)
        self._pending_key: str | None = None

    def get_layout(self):
        return [
            [self.key_input],
            [self.value_input],
            [self.cancel_btn],
        ]

    async def display(self, update: TuicanUpdate) -> None:
        if not self.service.is_admin(update.user_id or 0):
            await self.backend.send_plain_message(update, "⛔ This command is for admins only.")
            return
        await super().display(update)
        await self.set_focus(self.key_input)

    async def on_key_entered(self):
        key = self.key_input.value
        if key is None or key not in ALL_CONFIGURABLE_KEYS:
            await self.backend.send_plain_message(
                self.update,
                f"❌ `{key}` is not a configurable variable."
            )
            return
        self._pending_key = key
        await self.set_focus(self.value_input)

    async def do_set(self):
        key = self._pending_key
        value = self.value_input.value
        if key is None or value is None:
            return
        from dava.config import convert_value
        converted = convert_value(key, value)
        self.service.db.set_global_default(key, converted)
        await self.backend.send_plain_message(self.update, f"✅ Global default {key} set to {converted}")
        await self.go_home()

    async def on_command(self, args, update):
        if not self.service.is_admin(update.user_id or 0):
            await self.backend.send_plain_message(update, "⛔ This command is for admins only.")
            return
        if len(args) >= 2:
            name = args[0]
            val = args[1]
            if name not in ALL_CONFIGURABLE_KEYS:
                await self.backend.send_plain_message(update, f"❌ `{name}` is not a configurable variable.")
                return
            from dava.config import convert_value
            converted = convert_value(name, val)
            self.service.db.set_global_default(name, converted)
            await self.backend.send_plain_message(update, f"✅ Global default {name} set to {converted}")
            await self.go_home()
        else:
            await self.on_start(update)


class DeleteGlobalVariableScreen(DavaScreen):
    description: ClassVar[str] = "Delete Global Variable"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.key_input = Input[str](
            text="Variable name",
            validation_function=lambda x: x,
            on_change=self.do_delete,
            active_prompt="Enter global variable to delete: ",
        )
        self.cancel_btn = Button("❌ Cancel", on_change=self.go_home)
        super().__init__(group, service, message="Delete a global default")
        self.add_component(self.key_input)
        self.add_component(self.cancel_btn)

    def get_layout(self):
        return [[self.key_input], [self.cancel_btn]]

    async def display(self, update: TuicanUpdate) -> None:
        if not self.service.is_admin(update.user_id or 0):
            await self.backend.send_plain_message(update, "⛔ This command is for admins only.")
            return
        await super().display(update)
        await self.set_focus(self.key_input)

    async def do_delete(self):
        key = self.key_input.value
        if key is None:
            return
        self.service.db.delete_global_default(key)
        await self.backend.send_plain_message(self.update, f"✅ Global default {key} has been deleted")
        await self.go_home()

    async def on_command(self, args, update):
        if not self.service.is_admin(update.user_id or 0):
            await self.backend.send_plain_message(update, "⛔ This command is for admins only.")
            return
        if len(args) >= 1:
            name = args[0]
            self.service.db.delete_global_default(name)
            await self.backend.send_plain_message(update, f"✅ Global default {name} has been deleted")
            await self.go_home()
        else:
            await self.on_start(update)


class VideoModeScreen(DavaScreen):
    description: ClassVar[str] = "Video Mode"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.auto_btn = Button("✅ auto", on_change=self.set_auto)
        self.never_btn = Button("never", on_change=self.set_never)
        self.back_btn = Button("« Back", on_change=self.go_home)
        super().__init__(group, service)
        self.add_component(self.auto_btn)
        self.add_component(self.never_btn)
        self.add_component(self.back_btn)

    def get_layout(self):
        return [
            [self.auto_btn, self.never_btn],
            [self.back_btn],
        ]

    @property
    def message(self) -> str | None:
        user_id = self.current_user_id()
        current = self.service.get_effective_value(user_id, "video_mode") or "auto"
        return (
            f"Current video_mode: {current}\n\n"
            "Usage: /video_mode <auto|never>\n\n"
            "• `auto` — generate video on holidays and extreme weather\n"
            "• `never` — always generate static images"
        )

    async def display(self, update: TuicanUpdate) -> None:
        await super().display(update)

    async def set_auto(self):
        user_id = self.current_user_id()
        self.service.db.save_user_config(user_id, "video_mode", "auto")
        await self.backend.send_plain_message(self.update, "✅ video_mode set to auto")
        await self.go_home()

    async def set_never(self):
        user_id = self.current_user_id()
        self.service.db.save_user_config(user_id, "video_mode", "never")
        await self.backend.send_plain_message(self.update, "✅ video_mode set to never")
        await self.go_home()

    async def on_command(self, args, update):
        user_id = update.user_id or 0
        if len(args) >= 1 and args[0] in ("auto", "never"):
            self.service.db.save_user_config(user_id, "video_mode", args[0])
            await self.backend.send_plain_message(update, f"✅ video_mode set to {args[0]}")
            await self.go_home()
        else:
            await self.on_start(update)


class SetActionScreen(DavaScreen):
    description: ClassVar[str] = "Set Action"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.action_input = Input[str](
            text="Action",
            validation_function=lambda x: x,
            on_change=self.do_set,
            active_prompt="Enter action (weather|holiday code text): ",
        )
        self.cancel_btn = Button("❌ Cancel", on_change=self.go_home)
        super().__init__(group, service, message="Set a video action")
        self.add_component(self.action_input)
        self.add_component(self.cancel_btn)

    def get_layout(self):
        return [[self.action_input], [self.cancel_btn]]

    async def display(self, update: TuicanUpdate) -> None:
        await super().display(update)
        await self.set_focus(self.action_input)

    async def do_set(self):
        text = self.action_input.value
        if text is None:
            return
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()
        if len(parts) < 3 or parts[0] not in ("weather", "holiday"):
            await self.backend.send_plain_message(
                self.update,
                "Usage: /set_action <weather|holiday> <code_or_name> <action description>\n"
                "Example: /set_action weather 95 \"lightning flash, user flinches\""
            )
            return
        action_type = parts[0]
        key = parts[1]
        action_text = " ".join(parts[2:])
        user_id = self.current_user_id()
        result = self.service.apply_video_action(user_id, action_type, key, action_text)
        await self.backend.send_plain_message(self.update, result)
        await self.go_home()

    async def on_command(self, args, update):
        if len(args) >= 3:
            action_type = args[0]
            key = args[1]
            action_text = " ".join(args[2:])
            if action_type not in ("weather", "holiday"):
                await self.backend.send_plain_message(update, "Invalid action type. Use weather or holiday.")
                return
            user_id = update.user_id or 0
            result = self.service.apply_video_action(user_id, action_type, key, action_text)
            await self.backend.send_plain_message(update, result)
            await self.go_home()
        else:
            await self.on_start(update)


class DeleteActionScreen(DavaScreen):
    description: ClassVar[str] = "Delete Action"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.action_input = Input[str](
            text="Action to delete",
            validation_function=lambda x: x,
            on_change=self.do_delete,
            active_prompt="Enter action to delete (weather|holiday code): ",
        )
        self.cancel_btn = Button("❌ Cancel", on_change=self.go_home)
        super().__init__(group, service, message="Delete a video action")
        self.add_component(self.action_input)
        self.add_component(self.cancel_btn)

    def get_layout(self):
        return [[self.action_input], [self.cancel_btn]]

    async def display(self, update: TuicanUpdate) -> None:
        await super().display(update)
        await self.set_focus(self.action_input)

    async def do_delete(self):
        text = self.action_input.value
        if text is None:
            return
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()
        if len(parts) < 2 or parts[0] not in ("weather", "holiday"):
            await self.backend.send_plain_message(
                self.update,
                "Usage: /delete_action <weather|holiday> <code_or_name>\n"
                "Example: /delete_action holiday \"New Year's Day\""
            )
            return
        action_type = parts[0]
        key = parts[1]
        user_id = self.current_user_id()
        result = self.service.delete_video_action(user_id, action_type, key)
        await self.backend.send_plain_message(self.update, result)
        await self.go_home()

    async def on_command(self, args, update):
        if len(args) >= 2:
            action_type = args[0]
            key = args[1]
            if action_type not in ("weather", "holiday"):
                await self.backend.send_plain_message(update, "Invalid action type. Use weather or holiday.")
                return
            user_id = update.user_id or 0
            result = self.service.delete_video_action(user_id, action_type, key)
            await self.backend.send_plain_message(update, result)
            await self.go_home()
        else:
            await self.on_start(update)
