import logging
from typing import Dict, Any

from dava.weather_codes import codes as weather_codes
from dava.common import make_request
from dava.config import Config

logger = logging.getLogger(__name__)

class WeatherDescriptor:
    def __init__(self, config: Config):
        self._config = config
        self.base_url = "https://api.open-meteo.com/v1/forecast"

    async def get_forecast(self) -> Dict[str, Any]:
        weather_override = self._config.weather
        if weather_override:
            return weather_override
        response = await make_request(
            url=self.base_url,
            headers={},
            method="GET",
            params={
            "latitude": self._config.latitude,
            "longitude": self._config.longitude,
            "timezone": self._config.timezone,
            "current": ["weather_code", "is_day"]}
        )

        day = 'day' if response['current']['is_day'] > 0 else 'night'
        weather_code = str(response['current']['weather_code'])
        logger.info(response)

        if weather_code not in weather_codes:
            logger.warning(f"Unknown weather code: {weather_code}")
            weather_code = '2'  # default to Partly Cloudy
        return weather_codes[weather_code][day]
