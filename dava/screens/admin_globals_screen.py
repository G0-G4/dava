from typing import ClassVar

from tuican.components import Button, ScreenGroup

from dava.config import ADMIN_SETTING_CATEGORIES, ALL_CONFIGURABLE_KEYS
from dava.screens.base import DavaScreen
from dava.service import DavaService


class AdminGlobalsScreen(DavaScreen):
    description: ClassVar[str] = "Admin Globals"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.back_btn = Button("« Back", on_change=self.go_back)

        self._edit_buttons: list[Button] = []
        self._view_buttons: list[Button] = []

        super().__init__(group, service)
        self.add_component(self.back_btn)

    async def on_start(self, update):
        if not self.is_admin():
            await self.backend.send_plain_message(update, "⛔ This command is for admins only.")
            return
        await super().on_start(update)
        self._build_buttons()

    def _build_buttons(self):
        for btn in self._edit_buttons:
            self.delete_component(btn)
        for btn in self._view_buttons:
            self.delete_component(btn)
        self._edit_buttons = []
        self._view_buttons = []

        for cat_name, keys in ADMIN_SETTING_CATEGORIES.items():
            for key in keys:
                btn = Button(f"✏️ {key}", on_change=self._make_edit(key))
                self._edit_buttons.append(btn)
                self.add_component(btn)

                if self.service.is_complex_value(self.service.get_admin_value(key)):
                    view_btn = Button("👁 View full", on_change=self._make_view_full(key))
                    self._view_buttons.append(view_btn)
                    self.add_component(view_btn)

    def _make_edit(self, key: str):
        async def handler():
            from dava.screens.edit_screen import EditScreen
            await self.go_to_screen(EditScreen(self.group, self.service, key, is_global=True))
        return handler

    def _make_view_full(self, key: str):
        async def handler():
            from dava.screens.view_full_screen import ViewFullScreen
            await self.go_to_screen(ViewFullScreen(self.group, self.service, key, is_global=True))
        return handler

    def get_layout(self):
        rows: list = []
        for btn in self._edit_buttons:
            rows.append([btn])
        for btn in self._view_buttons:
            rows.append([btn])
        rows.append([self.back_btn])
        return rows

    @property
    def message(self) -> str | None:
        text_lines = ["**👑 Global defaults (affect all users)**"]
        for cat_name, keys in ADMIN_SETTING_CATEGORIES.items():
            text_lines.append(f"\n{cat_name}")
            for k in keys:
                disp = self.service.get_effective_display(0, k, truncate=80)
                text_lines.append(f"• {k}: {disp}")
        return "\n".join(text_lines)
