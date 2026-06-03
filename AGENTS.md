# AGENTS.md

## Project Overview

Telegram bot ("dava") that updates user profile photos based on current weather + optional holidays. Uses image generators (Stable Diffusion web or Polza.ai API) and the Telegram Bot API's Secretary Mode (business connection) to change profile photos. Also supports **video profile photos** via Veo 3.1 Fast (Polza.ai API), triggered by holidays and extreme weather conditions.

## Commands

- **Run**: `uv run main.py`
- **Run migrations**: `uv run scripts/run_migrations.py` (required before first run and after schema changes)
- **Tests**: `uv run pytest`
- **Single test file**: `uv run pytest tests/test_config.py`
- **With coverage**: `uv run pytest --cov=dava`
- **Python version**: 3.13 (enforced by `.python-version`)

## Architecture

- **Entrypoint**: `main.py` — creates `Config`, `Database`, `WeatherDescriptor`, `AvatarUpdater`, `BotController`; wires them together
- **Package**: `dava/` — all source code
  - `bot_controller.py` — Telegram bot handlers, scheduler, command routing, `/video_mode` command, video prompt preparation, `_should_generate_video()`. This is the main orchestration module
  - `avatar_updater.py` — generates image/video and uploads to Telegram via business connection. Handles video: `async_update_video_avatar()`, `_prepare_video()` (crop 9:16→1:1, truncate to 3s, extract first frame)
  - `config.py` — reads `.env`, defines config key categories (system/admin/user), enums, `convert_value()`. No default constants or migration methods (those moved to DB migrations)
  - `db.py` — synchronous SQLite (`sqlite3`), WAL mode, stores users, user_config, global_config, connections, schedules, image cache. `auto_create=False` by default; `_create_tables()` kept for migration use
  - `weather_descriptor.py` — fetches from Open-Meteo API, maps WMO codes to prompt-friendly descriptions. Returns `weather_code` in forecast dict
  - `weather_codes.py` — large dict mapping WMO weather codes → season × day/night prompt fragments
  - `holidays.py` — uses `workalendar` for Russian holidays, Friday 13th special case
  - `generators/` — `ImageGenerator` ABC with `StableDiffusionGenerator` (scrapes stablediffusionweb.com), `NanoBananaGenerator` (Polza.ai API), `VideoGenerator` ABC, `VeoGenerator` (Polza.ai REFERENCE_2_VIDEO), `PolzaBase` (shared Polza API logic)
  - `common.py` — shared async HTTP helper
  - `errors.py` — `RequestError`
  - `logs.py` — rotating file handler + in-memory ring buffer (used by `/logs` bot command)
- **Migrations**: `scripts/`
  - `run_migrations.py` — discovers and runs pending migrations, tracks applied ones in `schema_version` table
  - `migrations/001_initial_schema.py` — creates users, user_config, global_config tables
  - `migrations/002_seed_video_defaults.py` — seeds video_actions, video_prompt_text into global_config
  - `migrations/003_seed_app_defaults.py` — seeds application defaults (prompt_text, place, coords, etc.) into global_config

## Key Conventions & Gotchas

- Config is **tiered**: system keys (env-only), admin-only keys, user-configurable keys. User config resolves as: user override → global default → env fallback
- Config defaults (video_actions, video_prompt_text) are **seeded via migration** `002_seed_video_defaults.py`, not hardcoded in `config.py`. Bot code uses inline fallbacks for crash-safety if DB values are missing
- `.env` values are no longer migrated to DB; migration `003_seed_app_defaults.py` seeds hardcoded defaults
- `Config` is synchronous (reads env vars on property access), not a dataclass
- `Database` is **synchronous** (`sqlite3`), despite being used inside async handlers. No async DB driver.
- `Database.__init__` no longer auto-creates tables by default (`auto_create=False`). Migrations handle schema creation
- Telegram session file (`*.session`) is gitignored — bot uses `bot_token` auth, not phone login
- `data/` directory is gitignored (contains `bot.db` and user images)
- `logs/` and `images/` directories must exist before running (README mentions this)
- `ffmpeg` is a **system dependency** — used to crop video to 1:1 and truncate to 3s for Telegram compatibility
- Video model: `google/veo3_fast` only. Output is 9:16, center-cropped to 1:1 (`crop=min(iw,ih):min(iw,ih)`)
- Video is truncated to 3 seconds, audio stripped (`-an`), `+faststart` movflags — required for Telegram `VideoFileInvalidError`
- Telegram `UploadProfilePhotoRequest` requires both `file=` (static first frame JPG) and `video=` params
- `video_mode` values: `auto` (default — generate video on holidays/extreme weather), `never` (disable video generation)
- Video triggering is determined by `video_actions` keys: weather codes in `video_actions.weather` and holidays in `video_actions.holidays` both define *whether* to generate video and *what action* to use
- `ImageGenerators.NANO_BANANA_2` is the **default** when no generator is configured (see `generators/__init__.py`)
- Stable Diffusion generator crops top 4% of generated image (lines 124-125 in `stable_diffusion_generator.py`)
- Scheduler cron times are stored in UTC but user inputs are local times — potential timezone mismatch

## Testing

- `pytest-asyncio` with `asyncio_mode = "auto"` — async tests just work, no markers needed
- Fixtures in `conftest.py`: `tmp_data_dir`, `db`, `db_with_user`, `db_with_allowed_user`, `mock_config`, `mock_client`
- `db` fixture uses `auto_create=True` so tests don't need to run migrations
- Tests mock external APIs; no network calls needed
- `.env` secrets not required for tests — `Config` is mocked in fixtures

## Deployment

- `systemd/` contains `dava.service` and `dava.timer` for production
- Service runs `uv run avatar_updater.py` (note: this file doesn't exist locally, service file may be stale — `main.py` is the actual entrypoint)
- **Migrations must be run before first start**: `uv run scripts/run_migrations.py`