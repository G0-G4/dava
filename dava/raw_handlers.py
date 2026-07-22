import logging
from io import BytesIO

from telethon import events
from telethon.tl import types as tl_types

from dava.service import DavaService

logger = logging.getLogger(__name__)


class RawHandlers:
    def __init__(self, client, service: DavaService):
        self.client = client
        self.service = service
        self._setup_handlers()

    def _setup_handlers(self):
        @self.client.on(events.Raw(types=tl_types.UpdateBotBusinessConnect))
        async def business_connect_handler(update):
            connection = update.connection
            if not hasattr(connection, "connection_id") or not hasattr(connection, "user_id"):
                return

            rights = None
            if hasattr(connection, "rights") and connection.rights:
                rights = {
                    "edit_profile_photo": getattr(connection.rights, "edit_profile_photo", False),
                }

            user_id = connection.user_id
            self.service.db.save_connection(
                user_id=user_id,
                connection_id=connection.connection_id,
                tg_user_id=connection.user_id,
                rights=rights,
            )
            logger.info(f"Business connection established: {connection.connection_id} (user_id={user_id})")

            if self.service.db.is_allowed(user_id):
                has_photo_right = rights and rights.get("edit_profile_photo")
                status = "with" if has_photo_right else "without"
                await self.client.send_message(
                    user_id,
                    f"Business connection {status} profile photo editing rights.",
                )
            else:
                await self.client.send_message(
                    user_id,
                    "Your business connection has been received, but access has not been granted yet. "
                    "Please wait for the admin to approve your access.",
                )
                for admin_id in self.service.db.list_allowed():
                    if self.service.db.is_admin(admin_id):
                        await self.client.send_message(
                            admin_id,
                            f"New business connection request from user {user_id}. "
                            f"Use /grant {user_id} to allow access.",
                        )

        @self.client.on(events.NewMessage())
        async def handle_photo_upload(event):
            user_id = event.chat_id
            if not event.photo:
                return
            if not self.service.db.is_allowed(user_id):
                return

            if user_id in self.service._pending_upload:
                self.service._pending_upload.discard(user_id)
                try:
                    buf = BytesIO()
                    await event.download_media(file=buf)
                    result = await self.service.handle_photo_upload(user_id, buf.getvalue())
                    await event.respond(result)
                except Exception as e:
                    logger.exception(f"Failed to save base image for user {user_id}")
                    await event.respond(f"❌ Failed to save image: {str(e)}")

            elif user_id in self.service._pending_reference_upload:
                self.service._pending_reference_upload.discard(user_id)
                try:
                    buf = BytesIO()
                    await event.download_media(file=buf)
                    result = await self.service.handle_reference_photo_upload(user_id, buf.getvalue())
                    await event.respond(result)
                except Exception as e:
                    logger.exception(f"Failed to save reference image for user {user_id}")
                    await event.respond(f"❌ Failed to save reference image: {str(e)}")

        @self.client.on(events.NewMessage(pattern="/cancel"))
        async def cancel_pending(event):
            user_id = event.chat_id
            if not self.service.db.is_allowed(user_id):
                return
            cleared = False
            if user_id in self.service._pending_upload:
                self.service._pending_upload.discard(user_id)
                cleared = True
            if user_id in self.service._pending_reference_upload:
                self.service._pending_reference_upload.discard(user_id)
                cleared = True
            await event.respond("✅ Cancelled pending input." if cleared else "Nothing to cancel.")
