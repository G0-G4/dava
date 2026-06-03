import asyncio
import shutil
import subprocess
from pathlib import Path
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


def _ffmpeg_available():
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg/ffprobe not available")
class TestCropToSquare:
    @pytest.fixture
    def portrait_video(self, tmp_path):
        video_path = tmp_path / "portrait.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=720x1280:d=1:r=24",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
            "-pix_fmt", "yuv420p",
            str(video_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return str(video_path)

    @pytest.fixture
    def landscape_video(self, tmp_path):
        video_path = tmp_path / "landscape.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=1280x720:d=1:r=24",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
            "-pix_fmt", "yuv420p",
            str(video_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return str(video_path)

    async def test_crop_portrait_9_16_to_square(self, avatar_updater, portrait_video):
        result = await avatar_updater._crop_to_square(portrait_video)

        assert Path(result).exists()
        assert result.endswith("_1x1.mp4")
        assert Path(portrait_video).exists()

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0", result],
            capture_output=True, text=True, check=True,
        )
        parts = probe.stdout.strip().split(",")
        assert int(parts[0]) == int(parts[1]), f"Output is not square: {probe.stdout.strip()}"

    async def test_crop_landscape_16_9_to_square(self, avatar_updater, landscape_video):
        result = await avatar_updater._crop_to_square(landscape_video)

        assert Path(result).exists()
        assert result.endswith("_1x1.mp4")
        assert Path(landscape_video).exists()

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0", result],
            capture_output=True, text=True, check=True,
        )
        parts = probe.stdout.strip().split(",")
        assert int(parts[0]) == int(parts[1]), f"Output is not square: {probe.stdout.strip()}"

    async def test_portrait_crop_dimensions(self, avatar_updater, portrait_video):
        result = await avatar_updater._crop_to_square(portrait_video)

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0", result],
            capture_output=True, text=True, check=True,
        )
        parts = probe.stdout.strip().split(",")
        width, height = int(parts[0]), int(parts[1])
        assert width == 720, f"Expected width 720, got {width}"
        assert height == 720, f"Expected height 720, got {height}"

    async def test_landscape_crop_dimensions(self, avatar_updater, landscape_video):
        result = await avatar_updater._crop_to_square(landscape_video)

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0", result],
            capture_output=True, text=True, check=True,
        )
        parts = probe.stdout.strip().split(",")
        width, height = int(parts[0]), int(parts[1])
        assert width == 720, f"Expected width 720, got {width}"
        assert height == 720, f"Expected height 720, got {height}"


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg/ffprobe not available")
class TestTruncateVideo:
    @pytest.fixture
    def long_video(self, tmp_path):
        video_path = tmp_path / "long.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=green:s=720x1280:d=10:r=24",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
            "-pix_fmt", "yuv420p",
            str(video_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return str(video_path)

    @pytest.fixture
    def short_video(self, tmp_path):
        video_path = tmp_path / "short.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=yellow:s=720x1280:d=2:r=24",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
            "-pix_fmt", "yuv420p",
            str(video_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return str(video_path)

    async def test_truncate_long_video(self, avatar_updater, long_video):
        result = await avatar_updater._truncate_video(long_video)

        assert Path(result).exists()

        probe = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "csv=p=0", result],
            capture_output=True, text=True, check=True,
        )
        duration = float(probe.stdout.strip())
        assert duration <= 10, f"Expected duration <= 10s, got {duration:.1f}s"

    async def test_truncate_short_video_stays(self, avatar_updater, short_video):
        result = await avatar_updater._truncate_video(short_video)

        assert Path(result).exists()

        probe = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "csv=p=0", result],
            capture_output=True, text=True, check=True,
        )
        duration = float(probe.stdout.strip())
        assert duration <= 2.5, f"Short video should remain short, got {duration:.1f}s"


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg/ffprobe not available")
class TestExtractFirstFrame:
    @pytest.fixture
    def sample_video(self, tmp_path):
        video_path = tmp_path / "sample.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=720x1280:d=1:r=24",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
            "-pix_fmt", "yuv420p",
            str(video_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return str(video_path)

    async def test_extract_first_frame(self, avatar_updater, sample_video):
        result = await avatar_updater._extract_first_frame(sample_video)

        assert Path(result).exists()
        assert result.endswith(".jpg")
        assert Path(result).stat().st_size > 0

    async def test_extracted_frame_is_square(self, avatar_updater, sample_video):
        result = await avatar_updater._extract_first_frame(sample_video)

        probe = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0", result],
            capture_output=True, text=True, check=True,
        )
        assert probe.stdout.strip() != ""


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg/ffprobe not available")
class TestPrepareVideo:
    @pytest.fixture
    def long_video(self, tmp_path):
        video_path = tmp_path / "long_video.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=720x1280:d=10:r=24",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
            "-pix_fmt", "yuv420p",
            str(video_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return str(video_path)

    async def test_prepare_video_truncates_and_crops(self, avatar_updater, long_video):
        result = await avatar_updater._prepare_video(long_video)

        assert Path(result).exists()

        width, height = self._probe_dimensions(result)
        assert width == height, f"Video is not square: {width}x{height}"

        duration = self._probe_duration(result)
        assert duration <= 10, f"Video duration {duration:.1f}s exceeds 10s limit"

    def _probe_dimensions(self, video_path):
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, check=True,
        )
        parts = probe.stdout.strip().split(",")
        return int(parts[0]), int(parts[1])

    def _probe_duration(self, video_path):
        probe = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, check=True,
        )
        return float(probe.stdout.strip())