import logging
from typing import Dict, Any

import weather_codes
from common import make_request

logger = logging.getLogger(__name__)

class WeatherDescriptor:
    def __init__(self, latitude: float, longitude: float, timezone: str):
        self.latitude = latitude
        self.longitude = longitude
        self.timezone = timezone
        self.base_url = "https://api.open-meteo.com/v1/forecast"
        self.params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timezone": self.timezone,
            "current": ["weather_code", "is_day"],
        }

    async def get_forecast(self) -> Dict[str, Any]:
        response = await make_request(
            url=self.base_url,
            headers={},
            method="GET",
            params=self.params
        )

        day = 'day' if response['current']['is_day'] > 0 else 'night'
        weather_code = str(response['current']['weather_code'])

        if weather_code not in weather_codes.codes:
            logger.warning(f"Unknown weather code: {weather_code}")
            weather_code = '2'  # default to Partly Cloudy
        return weather_codes.codes[weather_code][day]
