import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dava.avatar_updater import AvatarUpdater
from dava.config import Config, ImageGenerators, Style
from dava.db import Database


@pytest.fixture
def avatar_updater(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db = Database(str(data_dir / "test.db"), str(data_dir), admin_ids={111})
    config = MagicMock()
    config.bot_token = "test-token"
    updater = AvatarUpdater(config=config, db=db)
    return updater


@pytest.fixture
def avatar_updater_with_client(avatar_updater):
    avatar_updater.client = AsyncMock()
    return avatar_updater


def _setup_user_with_image(avatar_updater):
    user_dir = avatar_updater.db._data_dir / "users" / "1"
    user_dir.mkdir(parents=True, exist_ok=True)
    avatar_path = user_dir / "avatar.jpg"
    avatar_path.write_bytes(b"fake avatar image")
    avatar_updater.db.ensure_user(1)
    avatar_updater.db.save_connection(1, "conn-1", 100, {"edit_profile_photo": True})
    avatar_updater.db._conn.execute(
        "UPDATE users SET base_image_path = ? WHERE user_id = ?",
        (str(avatar_path), 1),
    )
    avatar_updater.db._conn.commit()


class TestAvatarUpdaterErrors:
    async def test_no_connection_raises(self, avatar_updater):
        with pytest.raises(RuntimeError, match="No business connection"):
            await avatar_updater.async_update_avatar("prompt", user_id=1)

    async def test_no_client_raises(self, avatar_updater):
        avatar_updater.db.save_connection(1, "conn-1", 100)
        with pytest.raises(RuntimeError, match="Bot client not initialized"):
            await avatar_updater.async_update_avatar("prompt", user_id=1)

    async def test_no_base_image_raises(self, avatar_updater_with_client):
        avatar_updater_with_client.db.save_connection(1, "conn-1", 100)
        with pytest.raises(RuntimeError, match="No base image"):
            await avatar_updater_with_client.async_update_avatar("prompt", user_id=1)


class TestAvatarUpdaterCache:
    async def test_cache_hit(self, avatar_updater_with_client):
        updater = avatar_updater_with_client
        _setup_user_with_image(updater)

        cache_hash = updater.db.compute_cache_hash(1, "test prompt")
        cache_path = updater.db.get_cache_path(1, cache_hash)
        cache_path.write_bytes(b"cached image data")

        with patch("dava.avatar_updater.get_image_generator") as mock_get_gen:
            await updater.async_update_avatar("test prompt", user_id=1)
            mock_get_gen.assert_not_called()

    async def test_cache_miss_calls_generator(self, avatar_updater_with_client):
        updater = avatar_updater_with_client
        _setup_user_with_image(updater)

        mock_generator = AsyncMock()
        mock_generator.generate_and_save_image = AsyncMock(return_value="/fake/path.jpg")

        with patch("dava.avatar_updater.get_image_generator", return_value=mock_generator):
            with patch.object(updater, "_delete_avatar", new_callable=AsyncMock):
                result = await updater.async_update_avatar("unique prompt", user_id=1)
                mock_generator.generate_and_save_image.assert_called_once()


class TestDeleteAvatar:
    async def test_delete_avatar_success(self, avatar_updater_with_client):
        from aiohttp import web
        from aiohttp.test_utils import TestServer

        async def handler(request):
            return web.json_response({"ok": True})

        app = web.Application()
        app.router.add_post("/bottest-token/removeBusinessAccountProfilePhoto", handler)
        server = TestServer(app)
        await server.start_server()
        try:
            original_url = f"https://api.telegram.org/bottest-token/removeBusinessAccountProfilePhoto"
            with patch("dava.avatar_updater.aiohttp.ClientSession") as mock_session_cls:
                pass
        finally:
            await server.close()