from typing import ClassVar

from tuican.components import Button, Input, ScreenGroup
from tuican.update import TuicanUpdate

from dava.screens.base import DavaScreen
from dava.service import DavaService


class UsersScreen(DavaScreen):
    """Admin: list allowed users, open details, or grant access."""

    description: ClassVar[str] = "Users"
    PAGE_SIZE: ClassVar[int] = 8

    def __init__(self, group: ScreenGroup, service: DavaService, page: int = 0):
        self.page = page
        self.back_btn = Button("« Back", on_change=self.leave)
        self.grant_btn = Button("➕ Grant access", on_change=self.open_grant)

        self._user_buttons: list[Button] = []
        self._prev_btn: Button | None = None
        self._next_btn: Button | None = None

        super().__init__(group, service)
        self.add_component(self.back_btn)
        self.add_component(self.grant_btn)

    def _allowed_users(self) -> list[int]:
        return self.service.db.list_allowed()

    def _cleanup_dynamic(self) -> None:
        for btn in self._user_buttons:
            self.delete_component(btn)
        self._user_buttons = []
        if self._prev_btn is not None:
            self.delete_component(self._prev_btn)
            self._prev_btn = None
        if self._next_btn is not None:
            self.delete_component(self._next_btn)
            self._next_btn = None

    def _build_buttons(self) -> None:
        self._cleanup_dynamic()
        users = self._allowed_users()
        start = self.page * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        page_users = users[start:end]

        for uid in page_users:
            badge = " 👑" if self.service.db.is_admin(uid) else ""
            conn = "🔗" if self.service.db.load_connection(uid) else "—"
            img = "🖼" if self.service.db.has_base_image(uid) else "—"
            label = f"{uid}{badge} {conn}{img}"
            btn = Button(label, on_change=self._make_open_user(uid))
            self._user_buttons.append(btn)
            self.add_component(btn)

        if self.page > 0:
            self._prev_btn = Button("← Prev", on_change=self.go_prev)
            self.add_component(self._prev_btn)
        if end < len(users):
            self._next_btn = Button("Next →", on_change=self.go_next)
            self.add_component(self._next_btn)

    def _make_open_user(self, user_id: int):
        async def handler():
            await self.go_to_screen(UserDetailScreen(self.group, self.service, user_id))
        return handler

    async def open_grant(self):
        await self.go_to_screen(GrantUserScreen(self.group, self.service))

    async def leave(self):
        """Back to previous screen when nested; no-op if this is the command root."""
        update = self.update
        if update is None:
            return
        if len(self.group._screen_stack) > 1:
            await self.group.go_back(update)

    async def go_prev(self):
        if self.page > 0:
            self.page -= 1
            if self.update is not None:
                await self.display(self.update)

    async def go_next(self):
        self.page += 1
        if self.update is not None:
            await self.display(self.update)

    def get_layout(self):
        if not self.is_admin():
            return [[self.back_btn]]
        self._build_buttons()
        rows: list = [[btn] for btn in self._user_buttons]
        nav: list = []
        if self._prev_btn is not None:
            nav.append(self._prev_btn)
        if self._next_btn is not None:
            nav.append(self._next_btn)
        if nav:
            rows.append(nav)
        rows.append([self.grant_btn])
        rows.append([self.back_btn])
        return rows

    @property
    def message(self) -> str | None:
        if not self.is_admin():
            return "⛔ This command is for admins only."
        users = self._allowed_users()
        total = len(users)
        if total == 0:
            return (
                "**👥 Users with access** (empty)\n\n"
                "No allowed users yet. Use ➕ Grant access to add someone."
            )
        start = self.page * self.PAGE_SIZE + 1
        end = min((self.page + 1) * self.PAGE_SIZE, total)
        return (
            f"**👥 Users with access** ({start}–{end} of {total})\n"
            f"Tap a user to manage. 🔗 = connection, 🖼 = base image, 👑 = admin."
        )

    async def display(self, update: TuicanUpdate) -> None:
        if not self.service.is_admin(update.user_id or 0):
            await self.notify(update=update, text="⛔ This command is for admins only.")
            return
        await super().display(update)

    async def on_command(self, args, update: TuicanUpdate) -> None:
        await self.on_start(update)


class UserDetailScreen(DavaScreen):
    """Admin: view one user and optionally revoke access."""

    description: ClassVar[str] = "User"

    def __init__(self, group: ScreenGroup, service: DavaService, target_user_id: int):
        self.target_user_id = target_user_id
        self.back_btn = Button("« Back to list", on_change=self.go_back)
        self.revoke_btn = Button("🗑 Revoke access", on_change=self.do_revoke)

        super().__init__(group, service)
        self.add_component(self.back_btn)
        self.add_component(self.revoke_btn)

    def get_layout(self):
        rows: list = []
        # Don't offer revoke for admins (they stay allowed via admin_ids)
        if not self.service.db.is_admin(self.target_user_id):
            rows.append([self.revoke_btn])
        rows.append([self.back_btn])
        return rows

    @property
    def message(self) -> str | None:
        uid = self.target_user_id
        is_admin = self.service.db.is_admin(uid)
        allowed = self.service.db.is_allowed(uid)
        has_conn = self.service.db.load_connection(uid) is not None
        has_img = self.service.db.has_base_image(uid)
        has_ref = self.service.db.has_reference_image(uid)
        schedule = self.service.db.load_schedule(uid)

        lines = [
            f"**User `{uid}`**" + (" 👑 admin" if is_admin else ""),
            f"Access: {'✅ allowed' if allowed else '❌ revoked'}",
            f"Connection: {'✅' if has_conn else '❌'}",
            f"Base image: {'✅' if has_img else '❌'}",
            f"Scene reference: {'✅' if has_ref else '❌'}",
            f"Schedule: {', '.join(schedule) if schedule else '(none)'}",
        ]
        if is_admin:
            lines.append("\n_Admins cannot be revoked (always allowed)._")
        return "\n".join(lines)

    async def do_revoke(self):
        uid = self.target_user_id
        if self.service.db.is_admin(uid):
            await self.notify("❌ Cannot revoke admin access")
            return
        self.service.db.revoke(uid)
        self.service.remove_user_schedule(uid)
        await self.notify(f"✅ Revoked access from user {uid}")
        await self.go_back()


class GrantUserScreen(DavaScreen):
    """Admin: grant access by Telegram user id."""

    description: ClassVar[str] = "Grant"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.user_input = Input[str](
            text="User ID",
            validation_function=lambda x: x,
            on_change=self.do_grant,
            active_prompt="Enter user ID to grant: ",
        )
        self.back_btn = Button("« Back", on_change=self.go_back)
        super().__init__(
            group,
            service,
            message="**➕ Grant access**\n\nSend the Telegram user ID:",
        )
        self.add_component(self.user_input)
        self.add_component(self.back_btn)

    def get_layout(self):
        return [[self.user_input], [self.back_btn]]

    async def display(self, update: TuicanUpdate) -> None:
        if not self.service.is_admin(update.user_id or 0):
            await self.notify(update=update, text="⛔ This command is for admins only.")
            return
        await self.display_with_focus(update, self.user_input)

    async def do_grant(self):
        user_id_str = self.user_input.value
        if user_id_str is None:
            return
        try:
            target_user_id = int(str(user_id_str).strip())
        except ValueError:
            await self.notify("❌ Invalid user ID")
            return
        self.service.db.grant(target_user_id)
        self.service.restore_user_schedule(target_user_id)
        await self.notify(f"✅ Granted access to user {target_user_id}")
        await self.go_back()

    async def on_command(self, args, update: TuicanUpdate) -> None:
        if not self.service.is_admin(update.user_id or 0):
            await self.notify(update=update, text="⛔ This command is for admins only.")
            return
        if len(args) >= 1:
            try:
                target_user_id = int(args[0])
            except ValueError:
                await self.notify(update=update, text="❌ Invalid user ID")
                return
            self.service.db.grant(target_user_id)
            self.service.restore_user_schedule(target_user_id)
            await self.notify(update=update, text=f"✅ Granted access to user {target_user_id}")
            await self.go_home()
        else:
            await self.on_start(update)


class RevokeUserScreen(DavaScreen):
    """Admin: /revoke <user_id> CLI helper; UI revoke lives under Users."""

    description: ClassVar[str] = "Revoke"

    def __init__(self, group: ScreenGroup, service: DavaService):
        self.users_btn = Button("👥 Open users list", on_change=self.open_users)
        super().__init__(
            group,
            service,
            message=(
                "**🗑 Revoke access**\n\n"
                "Use **👥 Users** → tap a user → Revoke.\n"
                "Or: `/revoke <user_id>`"
            ),
        )
        self.add_component(self.users_btn)

    def get_layout(self):
        return [[self.users_btn]]

    async def open_users(self):
        await self.go_to_screen(UsersScreen(self.group, self.service))

    async def display(self, update: TuicanUpdate) -> None:
        if not self.service.is_admin(update.user_id or 0):
            await self.notify(update=update, text="⛔ This command is for admins only.")
            return
        await super().display(update)

    async def on_command(self, args, update: TuicanUpdate) -> None:
        if not self.service.is_admin(update.user_id or 0):
            await self.notify(update=update, text="⛔ This command is for admins only.")
            return
        if len(args) >= 1:
            try:
                target_user_id = int(args[0])
            except ValueError:
                await self.notify(update=update, text="❌ Invalid user ID")
                return
            if self.service.db.is_admin(target_user_id):
                await self.notify(update=update, text="❌ Cannot revoke admin access")
                return
            self.service.db.revoke(target_user_id)
            self.service.remove_user_schedule(target_user_id)
            await self.notify(update=update, text=f"✅ Revoked access from user {target_user_id}")
        # no args: on_start will show the hint + button to users list
