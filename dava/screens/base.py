from abc import ABC
from typing import ClassVar

from tuican.components import MessageHandlingComponent, Screen, ScreenGroup
from tuican.update import TuicanUpdate, get_user_id

from dava.service import DavaService


class DavaScreen(Screen, ABC):
    """Base screen for all dava screens. Provides access to service and navigation."""

    description: ClassVar[str] = ""

    def __init__(self, group: ScreenGroup, service: DavaService, message: str | None = None):
        self.group = group
        self.service = service
        super().__init__([], message=message)

    def current_user_id(self) -> int:
        update = self.update
        if update is None:
            raise RuntimeError("No active update")
        return get_user_id(update)

    def is_allowed(self) -> bool:
        return self.service.is_allowed(self.current_user_id())

    def is_admin(self) -> bool:
        return self.service.is_admin(self.current_user_id())

    async def display_with_focus(
        self,
        update: TuicanUpdate,
        focus_component: MessageHandlingComponent,
    ) -> None:
        """Render after ensuring a default input focus.

        Focus is applied only when nothing is currently accepting messages, and
        always *before* render so the active prompt matches message routing.
        Redisplays after the user toggles inputs therefore keep their choice.
        """
        if self._active_message_component is None:
            await self.set_focus(focus_component)
        await super().display(update)

    async def on_start(self, update: TuicanUpdate) -> None:
        await self.display(update)

    async def go_home(self) -> None:
        update = self.update
        if update is not None:
            await self.group.go_home(update)

    async def go_back(self) -> None:
        update = self.update
        if update is not None:
            await self.group.go_back(update)

    async def go_to_screen(self, screen: Screen) -> None:
        update = self.update
        if update is not None:
            await self.group.go_to_screen(update, screen)
