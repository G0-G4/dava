import requests

import weather_codes

PARAMS = {
    "latitude": 55.7522,
    "longitude": 37.6156,
    "timezone": "Europe/Moscow",
    "current": ["weather_code", "is_day"],
}
class WeatherDescriptor:
    def __init__(self):
        ...
    def get_forecast(self):
        url  = "https://api.open-meteo.com/v1/forecast"
        response = requests.get(url, params=PARAMS)
        if response.status_code != 200:
            raise RuntimeError(f"weather request failed: {response.text}")
        data = response.json()
        day = 'day' if data['current']['is_day'] > 0 else 'night'
        weather = weather_codes.codes[(str(data['current']['weather_code']))][day]
        weather = weather_codes.codes['96']['day']
        print(data)
        return weather

if __name__ == '__main__':
    w = WeatherDescriptor()
    print(w.get_forecast())