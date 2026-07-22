from typing import ClassVar

from tuican.components import Button, ScreenGroup

from dava.screens.base import DavaScreen
from dava.service import DavaService


class ActionPaginatorScreen(DavaScreen):
    """Paginated list of video actions for a category (weather/holidays)."""

    description: ClassVar[str] = "Action List"
    PAGE_SIZE: ClassVar[int] = 7

    def __init__(
        self,
        group: ScreenGroup,
        service: DavaService,
        category: str,  # "weather" or "holidays"
        page: int = 0,
    ):
        self.category = category
        self.page = page
        self.back_btn = Button("« Back", on_change=self.go_back)

        # Dynamic action buttons
        self._action_buttons: list[Button] = []

        super().__init__(group, service)
        self.add_component(self.back_btn)

    def _get_actions(self) -> dict[str, str]:
        user_id = self.current_user_id()
        return self.service.get_video_actions_category(user_id, self.category)

    def _build_page_buttons(self):
        # Cleanup old buttons
        for btn in self._action_buttons:
            self.delete_component(btn)
        self._action_buttons = []

        actions = self._get_actions()
        items = list(actions.items())  # [(key, value), ...]
        total = len(items)
        start = self.page * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        page_items = items[start:end]

        user_id = self.current_user_id()
        for key, value in page_items:
            date_suffix = ""
            if self.category == "holidays":
                md = self.service.get_holiday_date_for_name(user_id, key)
                if md:
                    date_suffix = f" [{md}]"
            label = f"{key}{date_suffix}: {value[:40]}{'…' if len(value) > 40 else ''}"
            btn = Button(label, on_change=self._make_open_editor(key, value))
            self._action_buttons.append(btn)
            self.add_component(btn)

        # Pagination controls
        self._prev_btn: Button | None = None
        self._next_btn: Button | None = None
        if self.page > 0:
            self._prev_btn = Button("← Prev", on_change=self.go_prev)
            self.add_component(self._prev_btn)
        if end < total:
            self._next_btn = Button("Next →", on_change=self.go_next)
            self.add_component(self._next_btn)

    def _make_open_editor(self, key: str, value: str):
        async def handler():
            from dava.screens.action_editor_screen import ActionEditorScreen
            await self.go_to_screen(
                ActionEditorScreen(self.group, self.service, self.category, key, value)
            )
        return handler

    async def go_prev(self):
        if self.page > 0:
            self.page -= 1
            await self.display(self.update)

    async def go_next(self):
        self.page += 1
        await self.display(self.update)

    def get_layout(self):
        self._build_page_buttons()
        rows: list = []
        for btn in self._action_buttons:
            rows.append([btn])
        nav_row = []
        if self._prev_btn:
            nav_row.append(self._prev_btn)
        if self._next_btn:
            nav_row.append(self._next_btn)
        if nav_row:
            rows.append(nav_row)
        rows.append([self.back_btn])
        return rows

    @property
    def message(self) -> str | None:
        actions = self._get_actions()
        total = len(actions)
        cat_label = "🌦️ Weather" if self.category == "weather" else "🎉 Holiday"
        if total == 0:
            return (
                f"**{cat_label} actions** (empty)\n"
                "No actions yet. Go back and use ➕ Add."
            )
        start = self.page * self.PAGE_SIZE + 1
        end = min((self.page + 1) * self.PAGE_SIZE, total)
        return f"**{cat_label} actions** ({start}–{end} of {total})\nTap an action to edit or delete it."
