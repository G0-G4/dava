import json
import logging
from datetime import datetime
from io import BytesIO

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from dava.avatar_updater import AvatarUpdater
from dava.config import (
    ADMIN_ONLY_KEYS,
    ADMIN_SETTING_CATEGORIES,
    ALL_CONFIGURABLE_KEYS,
    USER_CONFIGURABLE_KEYS,
    USER_SETTING_CATEGORIES,
    ImageGenerators,
    VideoGenerators,
    convert_value,
)
from dava.db import Database
from dava.generators import get_image_generator
from dava.holidays import HolidayChecker
from dava.logs import get_recent_logs
from dava.weather_descriptor import WeatherDescriptor
from dava.weather_codes import codes as weather_codes

logger = logging.getLogger(__name__)

# Keys under video_actions dict (must match seeded defaults / DB shape).
VIDEO_ACTION_TYPES = frozenset({"weather", "holidays"})


class DavaService:
    def __init__(
        self,
        config,
        db: Database,
        updater: AvatarUpdater,
        weather_descriptor: WeatherDescriptor,
    ):
        self._config = config
        self.db = db
        self.updater = updater
        self.weather_descriptor = weather_descriptor
        self.scheduler = AsyncIOScheduler()
        self.holiday_checker = HolidayChecker()
        self._running_jobs: set[int] = set()
        self._pending_upload: set[int] = set()
        self._pending_reference_upload: set[int] = set()

    def is_allowed(self, user_id: int) -> bool:
        return self.db.is_allowed(user_id)

    def is_admin(self, user_id: int) -> bool:
        return self.db.is_admin(user_id)

    def get_effective_value(self, user_id: int, key: str):
        return self.db.get_effective_value(user_id, key)

    def get_admin_value(self, key: str):
        return self.db.get_admin_value(key)

    def get_source_indicator(self, user_id: int, key: str) -> str:
        user_config = self.db.load_user_config(user_id)
        global_config = self.db.list_global_defaults()
        if key in user_config:
            return " (your override)"
        if key in global_config:
            return " (default)"
        return ""

    def get_effective_display(self, user_id: int, key: str, truncate: int = 100) -> str:
        val = self.get_effective_value(user_id, key)
        if val is None:
            return "(not set)"
        if isinstance(val, dict):
            try:
                n = len(val)
                if key == "video_actions":
                    va = self.load_video_actions(user_id)
                    w = len(va.get("weather", {}))
                    h = len(va.get("holidays", {}))
                    return f"dict ({w} weather + {h} holiday actions)"
                return f"dict ({n} keys)"
            except Exception:
                return "dict"
        if isinstance(val, (list, tuple)):
            return f"list ({len(val)} items)"
        s = str(val)
        if len(s) > truncate:
            return s[:truncate] + "…"
        return s

    def load_video_actions(self, user_id: int) -> dict:
        """Load effective video_actions as a mutable dict copy."""
        va = self.get_effective_value(user_id, "video_actions") or {}
        if isinstance(va, str):
            try:
                va = json.loads(va)
            except Exception:
                va = {}
        if not isinstance(va, dict):
            return {}
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in va.items()}

    def get_video_actions_category(self, user_id: int, category: str) -> dict[str, str]:
        """Return the weather/holidays map for a video_actions category."""
        va = self.load_video_actions(user_id)
        bucket = va.get(category, {})
        return dict(bucket) if isinstance(bucket, dict) else {}

    def apply_video_action(self, user_id: int, action_type: str, key: str, action_text: str) -> str:
        try:
            if action_type not in VIDEO_ACTION_TYPES:
                return f"❌ Invalid action type `{action_type}`. Use weather or holidays."
            va = self.load_video_actions(user_id)
            va.setdefault(action_type, {})[key] = action_text
            self.db.save_user_config(user_id, "video_actions", va)
            return f"✅ Set {action_type}/{key} action."
        except Exception as e:
            return f"❌ Failed: {e}"

    def delete_video_action(self, user_id: int, action_type: str, key: str) -> str:
        try:
            if action_type not in VIDEO_ACTION_TYPES:
                return f"❌ Invalid action type `{action_type}`. Use weather or holidays."
            va = self.load_video_actions(user_id)
            if action_type in va and key in va[action_type]:
                del va[action_type][key]
                if not va.get(action_type):
                    va.pop(action_type, None)
                self.db.save_user_config(user_id, "video_actions", va)
                return f"✅ Removed {action_type}/{key}."
            return "Action not found."
        except Exception as e:
            return f"❌ Failed: {e}"

    def build_settings_summary(self, user_id: int) -> str:
        user_config = self.db.load_user_config(user_id)
        global_config = self.db.list_global_defaults()
        is_admin = self.is_admin(user_id)

        lines = ["**Current settings** (effective values):"]

        for cat_name, keys in USER_SETTING_CATEGORIES.items():
            lines.append(f"\n{cat_name}")
            for k in keys:
                if k == "schedule":
                    continue
                ind = self.get_source_indicator(user_id, k)
                disp = self.get_effective_display(user_id, k)
                lines.append(f"• {k}: {disp}{ind}")

        schedule = self.db.load_schedule(user_id)
        sched_disp = ", ".join(schedule) if schedule else "(none)"
        lines.append(f"\n📅 Schedule: {sched_disp}")

        customs = [
            k for k in user_config
            if k not in USER_CONFIGURABLE_KEYS and k not in ADMIN_ONLY_KEYS and k != "schedule"
        ]
        if customs:
            lines.append("\n🔸 Custom keys:")
            for k in sorted(customs):
                disp = self.get_effective_display(user_id, k)
                lines.append(f"• {k}: {disp}")

        if is_admin:
            lines.append("\n👑 You are admin — use Admin category for globals.")

        lines.append("\nTap a category below to view/edit.")
        return "\n".join(lines)

    def build_category_text(self, user_id: int, cat: str) -> str:
        user_config = self.db.load_user_config(user_id)
        text_lines = []

        if cat == "schedule":
            schedule = self.db.load_schedule(user_id)
            text_lines.append("**📅 Your update schedule** (UTC times)")
            if schedule:
                text_lines.append("Current: " + ", ".join(schedule))
            else:
                text_lines.append("No times set.")
            text_lines.append("\nUse the buttons or /add_time /delete_time.")
            return "\n".join(text_lines)

        if cat == "globals" and self.is_admin(user_id):
            text_lines.append("**👑 Global defaults (affect all users)**")
            for cat_name, keys in ADMIN_SETTING_CATEGORIES.items():
                text_lines.append(f"\n{cat_name}")
                for k in keys:
                    disp = self.get_effective_display(user_id, k, truncate=80)
                    text_lines.append(f"• {k}: {disp}")
            return "\n".join(text_lines)

        keys = USER_SETTING_CATEGORIES.get(cat, [])
        if not keys:
            text_lines.append(f"Category: {cat}")
        else:
            text_lines.append(f"**{cat}** — tap Edit to change")
            for k in keys:
                ind = self.get_source_indicator(user_id, k)
                disp = self.get_effective_display(user_id, k, truncate=80)
                text_lines.append(f"• {k}{ind}: {disp}")

            if cat == "🎥 Video":
                va = self.load_video_actions(user_id)
                w = len(va.get("weather", {}))
                h = len(va.get("holidays", {}))
                text_lines.append(f"\nvideo_actions: {w} weather + {h} holiday entries")
                text_lines.append("Use buttons below or /set_action / /delete_action for quick edits.")

        return "\n".join(text_lines)

    def get_category_keys(self, cat: str) -> list[str]:
        if cat == "schedule":
            return []
        if cat == "globals":
            result = []
            for _cat_name, keys in ADMIN_SETTING_CATEGORIES.items():
                result.extend(keys)
            return result
        return list(USER_SETTING_CATEGORIES.get(cat, []))

    def validate_time(self, time_str: str) -> bool:
        try:
            datetime.strptime(time_str, "%H:%M")
            return True
        except ValueError:
            return False

    def resolve_image_params(self, user_id: int) -> dict:
        image_generator = self.get_admin_value("image_generator")
        if isinstance(image_generator, str):
            try:
                image_generator = ImageGenerators(image_generator)
            except ValueError:
                image_generator = None
        return {
            "image_generator": image_generator,
            "polza_model": self.get_admin_value("polza_model"),
            "style": self.get_admin_value("style"),
            "image_cfg_scale": self.get_admin_value("image_cfg_scale"),
            "image_url": self.get_admin_value("image_url"),
            "hermes_auth_path": self.get_admin_value("hermes_auth_path"),
            "hermes_xai_image_model": self.get_admin_value("hermes_xai_image_model"),
            "xai_auth_path": self.get_admin_value("xai_auth_path"),
        }

    async def update_avatar(self, user_id: int) -> str:
        if not self.db.is_allowed(user_id):
            logger.warning(f"Skipping scheduled update for {user_id}: access not granted")
            return "Access not granted"
        if not self.db.load_connection(user_id):
            logger.warning(f"Skipping scheduled update for {user_id}: no business connection")
            return "No business connection"
        if not self.db.has_base_image(user_id):
            logger.warning(f"Skipping scheduled update for {user_id}: no base image")
            return "No base image uploaded. Use /upload to send one."
        if user_id in self._running_jobs:
            logger.info(f"Job already running for user {user_id}")
            return "Update already in progress for you"
        self._running_jobs.add(user_id)
        try:
            weather = await self._get_weather(user_id)
            use_video, weather_code = await self._should_generate_video(weather, user_id)
            if use_video:
                ref_prompt = await self._prepare_prompt(user_id, weather)
                image_params = self.resolve_image_params(user_id)
                base_for_ref = self.db.get_base_image_path(user_id)
                ref_cache_hash = self.db.compute_cache_hash(user_id, ref_prompt, mode="image", reference_image_path=base_for_ref)
                ref_cached = self.db.check_cache(user_id, ref_cache_hash, mode="image")
                if ref_cached:
                    ref_image_path = ref_cached
                else:
                    ref_output_path = str(self.db.get_cache_path(user_id, ref_cache_hash, mode="image"))
                    img_generator = get_image_generator(
                        self._config,
                        image_generator=image_params["image_generator"],
                        polza_model=image_params["polza_model"],
                        style=image_params["style"],
                        image_cfg_scale=image_params["image_cfg_scale"],
                        image_url=image_params["image_url"],
                        hermes_auth_path=image_params.get("hermes_auth_path"),
                        hermes_xai_image_model=image_params.get("hermes_xai_image_model"),
                        xai_auth_path=image_params.get("xai_auth_path"),
                    )
                    ref_image_path = await img_generator.generate_and_save_image(
                        ref_prompt, base_for_ref, ref_output_path
                    )
                video_prompt = await self._prepare_video_prompt(user_id, weather, weather_code)
                video_gen = self.get_admin_value("video_generator")
                if isinstance(video_gen, str):
                    try:
                        video_gen = VideoGenerators(video_gen)
                    except ValueError:
                        video_gen = None
                await self.updater.async_update_video_avatar(
                    video_prompt, user_id,
                    video_generator=video_gen,
                    reference_image_path=ref_image_path,
                    hermes_auth_path=self.get_admin_value("hermes_auth_path"),
                    hermes_xai_video_model=self.get_admin_value("hermes_xai_video_model"),
                    xai_auth_path=self.get_admin_value("xai_auth_path"),
                )
                logger.info(f"User {user_id}: Video avatar updated!")
                return "✅ Video avatar updated!"
            else:
                scene_ref = self.db.get_reference_image_path(user_id)
                use_scene_ref = bool(scene_ref)
                prompt = await self._prepare_prompt(user_id, weather, include_place=not use_scene_ref)
                image_params = self.resolve_image_params(user_id)
                await self.updater.async_update_avatar(
                    prompt, user_id, reference_image_path=scene_ref, **image_params
                )
                logger.info(f"User {user_id}: Avatar updated! (scene_ref={use_scene_ref})")
                return "✅ Avatar updated!"
        except Exception as e:
            error = f"Error while updating avatar: {str(e)}"
            logger.exception(e)
            return error
        finally:
            self._running_jobs.discard(user_id)

    async def _prepare_prompt(
        self,
        user_id: int,
        weather: dict | None = None,
        *,
        include_place: bool = True,
        apply_holidays: bool = True,
    ) -> str:
        place = self.get_effective_value(user_id, "place") or ""
        holidays = self.get_effective_value(user_id, "holidays")
        prompt_template = self.get_effective_value(user_id, "prompt_text")

        if weather is None:
            weather = await self._get_weather(user_id)
        prompt = prompt_template or ""
        substitutions = {**(weather or {})}
        if include_place:
            substitutions["place"] = place
        else:
            substitutions["place"] = "the location shown in the reference image"

        if apply_holidays:
            holiday = self.holiday_checker.get_today_holiday(holidays)
            if holiday:
                substitutions["clothing"] = self.holiday_checker.get_clothing(holidays)
                substitutions["environmental_details"] = self.holiday_checker.get_details(holidays)

        for key, val in substitutions.items():
            prompt = prompt.replace("{" + key + "}", str(val))

        if not include_place:
            bg_guide = " Preserve the exact background, landmarks, scenery and overall composition from the reference image; only adapt weather, lighting, clothing and environmental effects."
            if bg_guide not in prompt:
                prompt = prompt.rstrip() + bg_guide

        logger.info(f"User {user_id}: Prepared prompt (include_place={include_place}, apply_holidays={apply_holidays}): {prompt}")
        return prompt

    async def _get_weather(self, user_id: int) -> dict | None:
        lat = self.get_effective_value(user_id, "latitude")
        lon = self.get_effective_value(user_id, "longitude")
        tz = self.get_effective_value(user_id, "timezone")
        weather_override = self.get_effective_value(user_id, "weather")
        try:
            return await self.weather_descriptor.get_forecast(
                latitude=float(lat) if lat else None,
                longitude=float(lon) if lon else None,
                timezone=tz,
                weather_override=weather_override,
            )
        except Exception:
            logger.warning(f"Could not fetch weather for user {user_id}")
            return None

    def _get_neutral_reference_weather(self, user_id: int) -> dict:
        month = datetime.now().month
        if month in [12, 1, 2]:
            season = "winter"
        elif month in [3, 4, 5]:
            season = "spring"
        elif month in [6, 7, 8]:
            season = "summer"
        else:
            season = "autumn"

        code = "0"
        day = "day"

        base = dict(weather_codes.get(code, weather_codes["0"])[season][day])
        base["weather_code"] = code
        return base

    async def _should_generate_video(self, weather: dict | None, user_id: int) -> tuple[bool, str | None]:
        video_mode = self.get_effective_value(user_id, "video_mode")
        if video_mode == "never":
            return False, None

        video_actions = self.load_video_actions(user_id)

        holidays = self.get_effective_value(user_id, "holidays")
        holiday = self.holiday_checker.get_today_holiday(holidays)

        holiday_actions = video_actions.get("holidays", {})
        if holiday and holiday in holiday_actions:
            return True, str(weather.get("weather_code", "")) if weather else None

        weather_actions = video_actions.get("weather", {})
        if weather:
            weather_code = str(weather.get("weather_code", ""))
            if weather_code in weather_actions:
                return True, weather_code

        return False, str(weather.get("weather_code", "")) if weather else None

    async def _prepare_video_prompt(self, user_id: int, weather: dict | None, weather_code: str | None) -> str:
        place = self.get_effective_value(user_id, "place") or ""
        holidays = self.get_effective_value(user_id, "holidays")
        prompt_template = self.get_effective_value(user_id, "video_prompt_text") or "{action}"

        if weather is None:
            weather = await self._get_weather(user_id) or {}
        holiday = self.holiday_checker.get_today_holiday(holidays)

        video_actions = self.load_video_actions(user_id)

        action = ""
        if holiday:
            holiday_actions = video_actions.get("holidays", {})
            action = holiday_actions.get(holiday, "")
        if not action and weather_code:
            weather_actions = video_actions.get("weather", {})
            action = weather_actions.get(weather_code, "")

        weather = {**weather, "place": place, "action": action}
        if holiday:
            weather["clothing"] = self.holiday_checker.get_clothing(holidays)
            weather["environmental_details"] = self.holiday_checker.get_details(holidays)

        prompt = prompt_template
        for key, val in weather.items():
            prompt = prompt.replace("{" + key + "}", str(val))
        logger.info(f"User {user_id}: Prepared video prompt: {prompt}")
        return prompt

    async def generate_and_save_reference(self, user_id: int) -> str:
        if not self.db.has_base_image(user_id):
            raise RuntimeError("No base image. Upload one first with /upload.")

        base_path = self.db.get_base_image_path(user_id)
        neutral_weather = self._get_neutral_reference_weather(user_id)
        ref_prompt = await self._prepare_prompt(
            user_id, neutral_weather, include_place=True, apply_holidays=False
        )

        image_params = self.resolve_image_params(user_id)
        cache_hash = self.db.compute_cache_hash(user_id, ref_prompt, mode="image", reference_image_path=base_path)
        cached = self.db.check_cache(user_id, cache_hash, mode="image")
        if cached:
            generated_path = cached
        else:
            output_path = str(self.db.get_cache_path(user_id, cache_hash, mode="image"))
            img_generator = get_image_generator(
                self._config,
                image_generator=image_params["image_generator"],
                polza_model=image_params["polza_model"],
                style=image_params["style"],
                image_cfg_scale=image_params["image_cfg_scale"],
                image_url=image_params["image_url"],
                hermes_auth_path=image_params.get("hermes_auth_path"),
                hermes_xai_image_model=image_params.get("hermes_xai_image_model"),
                xai_auth_path=image_params.get("xai_auth_path"),
            )
            generated_path = await img_generator.generate_and_save_image(
                ref_prompt, base_path, output_path
            )

        with open(generated_path, "rb") as f:
            ref_bytes = f.read()
        ref_path = await self.db.save_reference_image_bytes(user_id, ref_bytes)
        logger.info(f"User {user_id}: Scene reference baked and saved to {ref_path}")
        return ref_path

    def restore_user_schedule(self, user_id: int):
        schedule = self.db.load_schedule(user_id)
        for job in self.scheduler.get_jobs():
            if job.id.startswith(f"avatar_{user_id}_"):
                self.scheduler.remove_job(job.id)
        for time_str in schedule:
            hour, minute = map(int, time_str.split(":"))
            self.scheduler.add_job(
                self.update_avatar,
                "cron",
                hour=hour,
                minute=minute,
                timezone="UTC",
                max_instances=1,
                args=[user_id],
                id=f"avatar_{user_id}_{time_str}",
            )
        if schedule and self.scheduler.state == 0:
            self.scheduler.start()

    def remove_user_schedule(self, user_id: int):
        for job in self.scheduler.get_jobs():
            if job.id.startswith(f"avatar_{user_id}_"):
                self.scheduler.remove_job(job.id)

    def restore_all_schedules(self):
        for user_id in self.db.list_allowed():
            self.restore_user_schedule(user_id)

    def restart_scheduler(self, user_id: int):
        self.remove_user_schedule(user_id)
        self.restore_user_schedule(user_id)

    async def handle_photo_upload(self, user_id: int, photo_bytes: bytes) -> str:
        try:
            await self.db.save_base_image_bytes(user_id, photo_bytes)
            return "✅ Base image uploaded successfully!"
        except Exception as e:
            logger.exception(f"Failed to save base image for user {user_id}")
            return f"❌ Failed to save image: {str(e)}"

    async def handle_reference_photo_upload(self, user_id: int, photo_bytes: bytes) -> str:
        try:
            await self.db.save_reference_image_bytes(user_id, photo_bytes)
            return (
                "✅ Scene reference image uploaded successfully!\n"
                "It will now be used as the visual reference for background stability on updates."
            )
        except Exception as e:
            logger.exception(f"Failed to save reference image for user {user_id}")
            return f"❌ Failed to save reference image: {str(e)}"

    @staticmethod
    @staticmethod
    def get_help_text() -> str:
        return """🤖 Avatar Updater Bot Commands:

📸 Setup:
/upload - Upload base image (raw identity photo)
/upload_reference - Upload scene reference (you + stable background for place)
/generate_reference - Bake a scene reference using neutral clear conditions + current prompt + location (recommended for stable backgrounds)
/clear_reference - Remove the active scene reference
/connection - Show business connection status
/start - Connect via Settings > Chat Automation

⚙️ Settings:
/settings — Browse & edit by categories (📍 Location, ✍️ Prompts, 🎥 Video, 📅 Schedule, etc.)
/set_variable KEY VALUE — Direct set (power users)
/set_action <weather|holidays> CODE "action text" — Easy edit for video triggers
/delete_action <weather|holidays> CODE — Remove a video action
/cancel — Abort any pending value input

🔄 Updates:
/update - Force update now
/video_mode - Set video generation mode (auto/never)
/schedule - Show update schedule
/add_time - Add new update time
/delete_time - Delete update time

🌐 Other:
/weather - Show current weather
/help - Show this message

👑 Admin:
/grant <user_id> - Grant access
/revoke <user_id> - Revoke access
/list_users - List all users
/set_global_variable - Set global default
/logs - Show recent logs"""

    def get_logs(self, num: int = 50) -> str:
        logs = "\n".join(get_recent_logs(num))[-4096:]
        return logs

    async def get_weather_text(self, user_id: int) -> str:
        lat = self.get_effective_value(user_id, "latitude")
        lon = self.get_effective_value(user_id, "longitude")
        tz = self.get_effective_value(user_id, "timezone")
        weather_override = self.get_effective_value(user_id, "weather")
        try:
            weather = await self.weather_descriptor.get_forecast(
                latitude=float(lat) if lat else None,
                longitude=float(lon) if lon else None,
                timezone=tz,
                weather_override=weather_override,
            )
            return f"```{json.dumps(weather)}```"
        except Exception as e:
            return f"❌ Failed to get weather: {e}"

    def get_connection_text(self, user_id: int) -> str:
        connection = self.db.load_connection(user_id)
        if connection:
            return f"Business connection active:\nConnection ID: {connection['connection_id']}\nUser ID: {connection['user_id']}"
        return "No business connection found. Connect the bot via Settings > Chat Automation in Telegram."

    def get_users_text(self) -> str:
        allowed = self.db.list_allowed()
        if not allowed:
            return "No users with access."
        lines = []
        for uid in allowed:
            has_conn = "✅" if self.db.load_connection(uid) else "❌"
            has_img = "✅" if self.db.has_base_image(uid) else "❌"
            has_ref = "✅" if self.db.has_reference_image(uid) else "❌"
            is_admin = " 👑" if self.db.is_admin(uid) else ""
            lines.append(f"• {uid}{is_admin} | Connection: {has_conn} | Image: {has_img} | Ref: {has_ref}")
        return "Users with access:\n" + "\n".join(lines)

    def get_schedule_text(self, user_id: int) -> str:
        schedule = self.db.load_schedule(user_id)
        if not schedule:
            return "No scheduled times set"
        jobs = "\n".join(str(job) for job in self.scheduler.get_jobs() if job.id.startswith(f"avatar_{user_id}_"))
        return "Scheduled update times:\n" + "\n".join(schedule) + "\n\n" + jobs
