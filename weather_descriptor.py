import aiohttp
import logging
from typing import Dict, Any

import weather_codes
from errors import RequestError
from common import make_request

logger = logging.getLogger(__name__)

PARAMS = {
    "latitude": 55.7522,
    "longitude": 37.6156,
    "timezone": "Europe/Moscow",
    "current": ["weather_code", "is_day"],
}

class WeatherDescriptor:
    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1/forecast"

    async def get_forecast(self) -> Dict[str, Any]:
        try:
            response = await make_request(
                url=self.base_url,
                headers={},
                method="GET",
                params=PARAMS
            )
            
            if not isinstance(response, dict):
                raise RequestError("Invalid weather API response format")
            
            day = 'day' if response['current']['is_day'] > 0 else 'night'
            weather_code = str(response['current']['weather_code'])
            
            if weather_code not in weather_codes.codes:
                logger.warning(f"Unknown weather code: {weather_code}")
                weather_code = '96'  # default to thunderstorm
            
            return weather_codes.codes[weather_code][day]
            
        except Exception as e:
            raise RequestError(f"Weather request failed: {str(e)}") from e
