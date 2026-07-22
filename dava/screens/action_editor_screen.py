from typing import ClassVar

from tuican.components import Button, Input, ScreenGroup
from tuican.update import TuicanUpdate

from dava.screens.base import DavaScreen
from dava.service import DavaService, normalize_holiday_date


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
        self.clear_date_btn = Button("⏭ Clear date (standard)", on_change=self.clear_date)

        self.date_input = Input[str](
            text="Date MM-DD",
            validation_function=lambda x: x,
            on_change=self.save_date,
            active_prompt="Enter date MM-DD (or - for standard): ",
        )
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
        self.add_component(self.clear_date_btn)
        self.add_component(self.date_input)
        self.add_component(self.value_input)

    def get_layout(self):
        rows = []
        if self.category == "holidays":
            rows.append([self.date_input])
            rows.append([self.clear_date_btn])
        rows.append([self.value_input])
        rows.append([self.delete_btn])
        rows.append([self.back_btn])
        return rows

    def _build_message(self, user_id: int) -> str:
        label = "weather" if self.category == "weather" else "holiday"
        parts = [
            f"**Edit {label} action**",
            f"Key: `{self.key}`",
        ]
        if self.category == "holidays":
            date_val = self.service.get_holiday_date_for_name(user_id, self.key)
            if date_val:
                parts.append(f"Custom date: `{date_val}` (MM-DD)")
            else:
                parts.append(
                    "Custom date: _(none — standard calendar holiday or unset)_"
                )
            parts.append(
                "\nNon-standard holidays need **Date MM-DD** so the bot knows when to trigger. "
                "Send `-` or tap ⏭ for standard calendar holidays."
            )
        parts.append(
            f"\nCurrent description (copy, edit, send):\n```\n{self.current_value}\n```\n"
            "Edit date and/or description below."
        )
        return "\n".join(parts)

    async def display(self, update: TuicanUpdate) -> None:
        user_id = update.user_id or 0
        if self.category == "holidays":
            existing = self.service.get_holiday_date_for_name(user_id, self.key)
            self.date_input.value = existing or ""
        self.message = self._build_message(user_id)
        focus = self.date_input if self.category == "holidays" else self.value_input
        await self.display_with_focus(update, focus)

    async def clear_date(self):
        if self.category != "holidays":
            return
        user_id = self.current_user_id()
        err = self.service.set_holiday_date_for_name(user_id, self.key, "")
        if err:
            await self.notify(err)
            return
        self.date_input.value = ""
        await self.notify("✅ Custom date cleared (standard holiday)")
        await self.set_focus(self.value_input)

    async def save_date(self):
        """Persist calendar binding after date field is submitted."""
        if self.category != "holidays":
            return
        raw = self.date_input.value
        if raw is None:
            return
        normalized = normalize_holiday_date(raw)
        if normalized is None:
            await self.notify("❌ Date must be MM-DD (e.g. 03-08) or `-` for standard")
            return
        user_id = self.current_user_id()
        err = self.service.set_holiday_date_for_name(user_id, self.key, normalized)
        if err:
            await self.notify(err)
            return
        if normalized:
            await self.notify(f"✅ Date set to {normalized}")
        else:
            await self.notify("✅ Custom date cleared (standard holiday)")
        await self.set_focus(self.value_input)

    async def save_value(self):
        new_value = self.value_input.value
        if new_value is None:
            return
        if not str(new_value).strip():
            await self.notify("❌ Action description cannot be empty")
            return
        user_id = self.current_user_id()
        holiday_date: str | None = None
        if self.category == "holidays":
            raw = self.date_input.value
            # Prefer stored field; empty string means clear custom date
            if raw is None:
                holiday_date = self.service.get_holiday_date_for_name(user_id, self.key) or ""
            else:
                normalized = normalize_holiday_date(raw)
                if normalized is None:
                    await self.notify("❌ Date must be MM-DD (e.g. 03-08) or `-` for standard")
                    return
                holiday_date = normalized
        result = self.service.apply_video_action(
            user_id,
            self.category,
            self.key,
            str(new_value).strip(),
            holiday_date=holiday_date,
        )
        if result.startswith("✅"):
            await self.notify("✅ Saved")
        else:
            await self.notify(result)
        await self.go_back()

    async def do_delete(self):
        user_id = self.current_user_id()
        result = self.service.delete_video_action(user_id, self.category, self.key)
        if result.startswith("✅"):
            await self.notify("🗑 Deleted")
        else:
            await self.notify(result)
        await self.go_back()
