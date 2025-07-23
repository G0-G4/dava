import aiohttp
import asyncio
import aiofiles
import base64
import logging
import time
from pathlib import Path
from typing import Dict, Any

from config import COOKIES, IMAGE_DIR, PLACE, PROMPT_TEXT
from errors import RequestError
from weather_descriptor import WeatherDescriptor
from common import make_request

logger = logging.getLogger(__name__)



HEADERS_TEMPLATE = {
    'accept': '*/*',
    'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'cache-control': 'no-cache',
    'content-type': 'application/json',
    'origin': 'https://stablediffusionweb.com',
    'pragma': 'no-cache',
    'priority': 'u=1, i',
    'referer': 'https://stablediffusionweb.com/ru/app/image-to-image',
    'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
}

IMAGE_CONFIG = {
    "steps": 40,
    "width": 1024,
    "height": 1024,
    "number_of_images": 1,
    "image_cfg_scale": 0.5
}
class AvatarGenerator:
    def __init__(self, cookies: str, image_dir: str, prompt: str, place: str, weather_descriptor: WeatherDescriptor):
        self.image_dir = Path(image_dir)
        self.headers = {**HEADERS_TEMPLATE, 'Cookie': cookies}
        self.prompt = prompt
        self.place = place
        self.weather_descriptor = weather_descriptor

    def _get_and_encode_image(self) -> str:
        with open(self.image_dir / 'avatar.jpg', 'rb') as image:
            image_b64 = base64.b64encode(image.read()).decode()
            return f"data:image/jpeg;base64,{image_b64}"

    async def _create_task(self, image_b64: str):
        url = "https://stablediffusionweb.com/api/generate.image.addTasks?batch=1"
        task_data = {
            "0": {
                "json": {
                    "model": "SD-XL",
                    "prompt": self._prepare_prompt(),
                    "negative_prompt": "",
                    **IMAGE_CONFIG,
                    "input_image": image_b64
                }
            }
        }
        return await make_request(url, self.headers, "POST", task_data)

    def _prepare_prompt(self):
        weather = self.weather_descriptor.get_forecast()
        prompt = self.prompt
        weather = {**weather, "place": self.place}
        for key, val in weather.items():
            prompt = prompt.replace('{'+key+'}', val)
        print(prompt)
        return prompt

    async def _check_status(self, uuid: str):
        url = "https://stablediffusionweb.com/api/generate.image.getTasks?batch=1"
        check_data = {
            "0": {
                "json": [{"uuid": uuid, "status": "new"}]
            }
        }
        return await make_request(url, self.headers, "POST", check_data)

    async def _get_image_url(self) -> str:
        try:
            image = self._get_and_encode_image()
            task_response = await self._create_task(image)
            uuid = task_response[0]['result']['data']['json'][0]['uuid']
            
            for _ in range(60):  # 1 minute timeout
                response = await self._check_status(uuid)
                status = response[0]['result']['data']['json'][0]['status']
                
                if status == "completed":
                    return response[0]['result']['data']['json'][0]['s3_url']
                if status == "failed":
                    raise RequestError("Image generation failed on server")
                
                await asyncio.sleep(1)
            
            raise RequestError("Image generation timed out")
        except Exception as e:
            raise RequestError(f"Failed getting image URL: {str(e)}") from e

    async def save_image(self) -> str:
        try:
            image_url = await self._get_image_url()
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status != 200:
                        raise RequestError(f"Image download failed: {response.status}")
                    
                    timestamp = int(time.time())
                    save_path = self.image_dir / f"avatar_{timestamp}.jpg"
                    
                    async with aiofiles.open(save_path, 'wb') as f:
                        await f.write(await response.read())
                    
                    return str(save_path.absolute())
        except Exception as e:
            raise RequestError(f"Failed saving image: {str(e)}") from e



async def main():
    g = AvatarGenerator(COOKIES, IMAGE_DIR, WeatherDescriptor())
    await g.save_image()

if __name__ == '__main__':
    asyncio.run(main())
