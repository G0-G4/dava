from typing import ClassVar

from tuican.components import Button, ScreenGroup

from dava.screens.base import DavaScreen
from dava.service import DavaService


class CategoryScreen(DavaScreen):
    description: ClassVar[str] = "Category"

    def __init__(self, group: ScreenGroup, service: DavaService, category: str):
        self.category = category
        self.back_btn = Button("« Back", on_change=self.go_back)

        # Buttons will be built dynamically
        self._edit_buttons: list[Button] = []
        self._view_buttons: list[Button] = []
        self._toggle_buttons: list[Button] = []
        self._action_buttons: list[Button] = []

        super().__init__(group, service)
        self.add_component(self.back_btn)

    def _cleanup_buttons(self):
        for btn in self._edit_buttons:
            self.delete_component(btn)
        for btn in self._view_buttons:
            self.delete_component(btn)
        for btn in self._toggle_buttons:
            self.delete_component(btn)
        for btn in self._action_buttons:
            self.delete_component(btn)
        self._edit_buttons.clear()
        self._view_buttons.clear()
        self._toggle_buttons.clear()
        self._action_buttons.clear()

    def _build_buttons(self):
        self._cleanup_buttons()
        user_id = self.current_user_id()
        keys = self.service.get_category_keys(self.category)

        for key in keys:
            if key == "video_mode":
                current = self.service.get_effective_value(user_id, "video_mode") or "auto"
                auto_text = "✅ auto" if current == "auto" else "auto"
                never_text = "✅ never" if current == "never" else "never"
                btn_auto = Button(auto_text, on_change=self._make_toggle_video_mode("auto"))
                btn_never = Button(never_text, on_change=self._make_toggle_video_mode("never"))
                self._toggle_buttons.extend([btn_auto, btn_never])
                self.add_component(btn_auto)
                self.add_component(btn_never)
            elif key == "video_actions":
                pass
            else:
                edit_label = f"✏️ Edit {key}"
                if key == "video_prompt_text":
                    edit_label = "✏️ Edit video prompt"
                elif key == "prompt_text":
                    edit_label = "✏️ Edit prompt"

                btn = Button(edit_label, on_change=self._make_edit(key))
                self._edit_buttons.append(btn)
                self.add_component(btn)

                if self.service.should_offer_view_full(user_id, key):
                    view_btn = Button("👁 View full", on_change=self._make_view_full(key))
                    self._view_buttons.append(view_btn)
                    self.add_component(view_btn)

        if self.category == "🎥 Video":
            manage_btn = Button("🎬 Manage video actions", on_change=self.open_video_actions)
            self._action_buttons.append(manage_btn)
            self.add_component(manage_btn)

    def _make_edit(self, key: str):
        async def handler():
            from dava.screens.edit_screen import EditScreen
            await self.go_to_screen(EditScreen(self.group, self.service, key))
        return handler

    def _make_view_full(self, key: str):
        async def handler():
            from dava.screens.view_full_screen import ViewFullScreen
            await self.go_to_screen(ViewFullScreen(self.group, self.service, key))
        return handler

    def _make_toggle_video_mode(self, value: str):
        async def handler():
            user_id = self.current_user_id()
            self.service.db.save_user_config(user_id, "video_mode", value)
            # Refresh the screen
            self._toggle_buttons.clear()
            self._build_buttons()
            update = self.update
            if update is not None:
                await self.display(update)
        return handler

    async def open_video_actions(self):
        from dava.screens.video_actions_main_screen import VideoActionsMainScreen
        await self.go_to_screen(VideoActionsMainScreen(self.group, self.service))

    def get_layout(self):
        self._build_buttons()
        rows: list = []
        for btn in self._edit_buttons:
            rows.append([btn])
        for btn in self._view_buttons:
            rows.append([btn])
        if self._toggle_buttons:
            rows.append(self._toggle_buttons)
        for btn in self._action_buttons:
            rows.append([btn])
        rows.append([self.back_btn])
        return rows

    @property
    def message(self) -> str | None:
        return self.service.build_category_text(self.current_user_id(), self.category)
