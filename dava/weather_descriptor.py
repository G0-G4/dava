import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict

from dava.common import make_request
from dava.errors import RequestError
from dava.weather_codes import codes as weather_codes

logger = logging.getLogger(__name__)

_USER_AGENT = "dava-dynamic-avatar/0.1"
_RETRYABLE_STATUS_MARKERS = (" 429 ", " 500 ", " 502 ", " 503 ", " 504 ")
_MAX_ATTEMPTS = 3


def _coerce_coord(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".", 1)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _coerce_override(weather_override) -> dict | None:
    if isinstance(weather_override, str):
        try:
            weather_override = json.loads(weather_override)
        except json.JSONDecodeError:
            return None
    if isinstance(weather_override, dict) and weather_override:
        return weather_override
    return None


def _season_for_month(month: int) -> str:
    if month in [12, 1, 2]:
        return "winter"
    if month in [3, 4, 5]:
        return "spring"
    if month in [6, 7, 8]:
        return "summer"
    return "autumn"


class WeatherDescriptor:
    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1/forecast"

    async def get_forecast(
        self,
        latitude: float | str | None = None,
        longitude: float | str | None = None,
        timezone: str | None = None,
        weather_override: dict | str | None = None,
    ) -> Dict[str, Any]:
        override = _coerce_override(weather_override)
        if override is not None:
            return override

        latitude = _coerce_coord(latitude)
        longitude = _coerce_coord(longitude)
        if isinstance(timezone, str):
            timezone = timezone.strip() or None
        timezone = timezone or "auto"

        if latitude is None or longitude is None:
            raise RuntimeError("latitude and longitude are required when weather_override is not provided")

        current_tz = timezone
        last_error: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = await self._fetch_current(latitude, longitude, current_tz)
                return self._map_forecast(response)
            except RequestError as e:
                last_error = e
                msg = str(e)
                if " 400 " in msg and "timezone" in msg.lower() and current_tz != "auto":
                    logger.warning("Invalid timezone %r for Open-Meteo, retrying with auto", current_tz)
                    current_tz = "auto"
                    continue
                retryable = msg.startswith("Network error") or any(m in msg for m in _RETRYABLE_STATUS_MARKERS)
                if retryable and attempt < _MAX_ATTEMPTS - 1:
                    delay = 2 ** attempt
                    logger.warning(
                        "Weather request failed (attempt %s/%s): %s; retrying in %ss",
                        attempt + 1, _MAX_ATTEMPTS, e, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise
        raise last_error or RequestError("Weather request failed")

    async def _fetch_current(self, latitude: float, longitude: float, timezone: str) -> dict:
        return await make_request(
            url=self.base_url,
            headers={"User-Agent": _USER_AGENT},
            method="GET",
            timeout=15,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "timezone": timezone,
                "current": "weather_code,is_day",
            },
        )

    def _map_forecast(self, response: dict) -> dict:
        current = response.get("current")
        if not isinstance(current, dict) or "weather_code" not in current or "is_day" not in current:
            raise RequestError(f"Unexpected Open-Meteo response: {response!r}")

        day = "day" if current["is_day"] > 0 else "night"
        weather_code = str(current["weather_code"])
        logger.debug("Open-Meteo current: %s", current)

        season = _season_for_month(datetime.now().month)
        if weather_code not in weather_codes:
            logger.warning(f"Unknown weather code: {weather_code}")
            weather_code = "2"
        result = dict(weather_codes[weather_code][season][day])
        result["weather_code"] = weather_code
        return result