from typing import ClassVar

from tuican.components import Button, ScreenGroup

from dava.screens.base import DavaScreen
from dava.service import DavaService


class ViewFullScreen(DavaScreen):
    description: ClassVar[str] = "View Full"

    def __init__(self, group: ScreenGroup, service: DavaService, key: str, is_global: bool = False):
        self.key = key
        self.is_global = is_global
        self.back_btn = Button("« Back", on_change=self.go_back)

        super().__init__(group, service)
        self.add_component(self.back_btn)

    @property
    def message(self) -> str | None:
        user_id = self.current_user_id()
        if self.is_global:
            val = self.service.get_admin_value(self.key)
        else:
            user_config = self.service.db.load_user_config(user_id)
            global_config = self.service.db.list_global_defaults()
            if self.key in user_config:
                source = "your override"
                val = user_config[self.key]
            elif self.key in global_config:
                source = "default"
                val = global_config[self.key]
            else:
                source = ""
                val = "(not set)"
        return self.service.format_long(f"{'🔒 ' if self.is_global else ''}{self.key} ({source if not self.is_global else 'global'})", val)

    def get_layout(self):
        return [[self.back_btn]]
