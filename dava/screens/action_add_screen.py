from typing import ClassVar

from tuican.components import Button, Input, ScreenGroup
from tuican.update import TuicanUpdate

from dava.screens.base import DavaScreen
from dava.service import DavaService, normalize_holiday_date


class ActionAddScreen(DavaScreen):
    """Screen to add a new video action (weather code or holiday name + description)."""

    description: ClassVar[str] = "Add Action"

    def __init__(
        self,
        group: ScreenGroup,
        service: DavaService,
        category: str,  # "weather" or "holidays"
    ):
        self.category = category
        self._holiday_date: str = ""  # "" = standard / no custom date
        self.back_btn = Button("« Back", on_change=self.go_back)

        is_weather = category == "weather"
        key_label = "Weather code (e.g. 95)" if is_weather else 'Holiday name (e.g. "Birthday")'
        self.key_input = Input[str](
            text=key_label,
            validation_function=lambda x: x,
            on_change=self.on_key_entered,
            active_prompt="Enter key: ",
        )
        self.date_input = Input[str](
            text="Date MM-DD",
            validation_function=lambda x: x,
            on_change=self.on_date_entered,
            active_prompt="Enter date MM-DD (or - for standard): ",
        )
        self.skip_date_btn = Button("⏭ Standard holiday (no date)", on_change=self.skip_date)
        self.value_input = Input[str](
            text="Action description",
            validation_function=lambda x: x,
            on_change=self.do_save,
            active_prompt="Enter description: ",
        )

        label = "weather" if is_weather else "holiday"
        super().__init__(group, service, message=self._intro_message(label))
        self.add_component(self.back_btn)
        self.add_component(self.key_input)
        self.add_component(self.date_input)
        self.add_component(self.skip_date_btn)
        self.add_component(self.value_input)

    def _intro_message(self, label: str) -> str:
        if self.category == "weather":
            return f"**➕ Add {label} action**\n\nEnter weather code, then description."
        return (
            f"**➕ Add {label} action**\n\n"
            "1. Holiday **name** (label in prompts / video_actions)\n"
            "2. **Date** `MM-DD` for custom days (e.g. birthday). "
            "For standard calendar holidays tap ⏭ or send `-`\n"
            "3. Action **description** for the video"
        )

    def get_layout(self):
        rows = [[self.key_input]]
        if self.category == "holidays":
            rows.append([self.date_input])
            rows.append([self.skip_date_btn])
        rows.append([self.value_input])
        rows.append([self.back_btn])
        return rows

    async def display(self, update: TuicanUpdate) -> None:
        await self.display_with_focus(update, self.key_input)

    async def on_key_entered(self):
        key = self.key_input.value
        if key is None:
            return
        if not key.strip():
            await self.notify("❌ Key cannot be empty")
            return
        if self.category == "holidays":
            await self.set_focus(self.date_input)
        else:
            await self.set_focus(self.value_input)

    async def on_date_entered(self):
        raw = self.date_input.value
        if raw is None:
            return
        normalized = normalize_holiday_date(raw)
        if normalized is None:
            await self.notify("❌ Date must be MM-DD (e.g. 03-08) or `-` for standard")
            return
        self._holiday_date = normalized
        await self.set_focus(self.value_input)

    async def skip_date(self):
        """Standard calendar holiday — no MM-DD override."""
        self._holiday_date = ""
        self.date_input.value = "-"
        await self.set_focus(self.value_input)

    async def do_save(self):
        key = self.key_input.value
        value = self.value_input.value
        if key is None or not key.strip() or value is None:
            return
        if not value.strip():
            await self.notify("❌ Action description cannot be empty")
            return

        holiday_date: str | None = None
        if self.category == "holidays":
            holiday_date = self._holiday_date
            # Prefer latest date field if user typed without going through handler state
            if self.date_input.value is not None:
                normalized = normalize_holiday_date(self.date_input.value)
                if normalized is None:
                    await self.notify("❌ Date must be MM-DD (e.g. 03-08) or `-` for standard")
                    return
                holiday_date = normalized

        user_id = self.current_user_id()
        result = self.service.apply_video_action(
            user_id,
            self.category,
            key.strip(),
            value.strip(),
            holiday_date=holiday_date,
        )
        if result.startswith("✅"):
            await self.notify(f"✅ Added {self.category}/{key}")
        else:
            await self.notify(result)
        await self.go_back()
