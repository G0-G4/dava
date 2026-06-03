import logging
from typing import Dict, Any
from datetime import datetime

from dava.weather_codes import codes as weather_codes
from dava.common import make_request

logger = logging.getLogger(__name__)


class WeatherDescriptor:
    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1/forecast"

    async def get_forecast(
        self,
        latitude: float | None = None,
        longitude: float | None = None,
        timezone: str | None = None,
        weather_override: dict | None = None,
    ) -> Dict[str, Any]:
        if weather_override:
            return weather_override

        if latitude is None or longitude is None or timezone is None:
            raise RuntimeError("latitude, longitude, and timezone are required when weather_override is not provided")

        response = await make_request(
            url=self.base_url,
            headers={},
            method="GET",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "timezone": timezone,
                "current": ["weather_code", "is_day"],
            },
        )

        day = 'day' if response['current']['is_day'] > 0 else 'night'
        weather_code = str(response['current']['weather_code'])
        logger.info(response)

        month = datetime.now().month
        if month in [12, 1, 2]:
            season = 'winter'
        elif month in [3, 4, 5]:
            season = 'spring'
        elif month in [6, 7, 8]:
            season = 'summer'
        else:
            season = 'autumn'

        if weather_code not in weather_codes:
            logger.warning(f"Unknown weather code: {weather_code}")
            weather_code = '2'
        result = dict(weather_codes[weather_code][season][day])
        result["weather_code"] = weather_code
        return result