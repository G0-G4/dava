from typing import ClassVar

from tuican.components import Button, ScreenGroup

from dava.config import ADMIN_SETTING_CATEGORIES
from dava.screens.base import DavaScreen
from dava.service import DavaService


class AdminGlobalsScreen(DavaScreen):
    description: ClassVar[str] = "Admin Globals"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.back_btn = Button("« Back", on_change=self.go_back)

        self._edit_buttons: list[Button] = []

        super().__init__(group, service)
        self.add_component(self.back_btn)

    def _build_buttons(self):
        for btn in self._edit_buttons:
            self.delete_component(btn)
        self._edit_buttons = []

        for cat_name, keys in ADMIN_SETTING_CATEGORIES.items():
            for key in keys:
                btn = Button(f"✏️ {key}", on_change=self._make_edit(key))
                self._edit_buttons.append(btn)
                self.add_component(btn)

    def _make_edit(self, key: str):
        async def handler():
            from dava.screens.edit_screen import EditScreen
            await self.go_to_screen(EditScreen(self.group, self.service, key, is_global=True))
        return handler

    def get_layout(self):
        if not self.is_admin():
            return [[self.back_btn]]
        self._build_buttons()
        rows: list = []
        for btn in self._edit_buttons:
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
