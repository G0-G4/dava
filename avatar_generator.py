import base64
import json
import time

import requests
class AvatarGenerator:
    def __init__(self):
        self.url = "stablediffusionweb.com"
        self.headers = {
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
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'Cookie': 'change me'
        }
        self.create_task_data = {
            "0": {
                "json": {
                    "model": "SD-XL",
                    "prompt": "A portrait of a person, set in egypt, during 12:00 with sunny weather conditions. The background reflects the local landscape and lighting. The mood should match the atmosphere. Include subtle environmental effects like fog, snow, rain, or sun glare.",
                    "negative_prompt": "",
                    "steps": 40,
                    "style": "Default",
                    "width": 1024,
                    "height": 1024,
                    "number_of_images": 1,
                    "cfg_scale": None,
                    "image_cfg_scale": 0.5,
                    "seed": None,
                    "input_image": None
                },
                "meta": {
                    "values": {
                        "cfg_scale": [
                            "undefined"
                        ],
                        "seed": [
                            "undefined"
                        ]
                    }
                }
            }
        }
        self.check_data = {
            "0": {
                "json": [
                    {
                        "uuid": None,
                        "status": "new"

                    }
                ]
            }
        }

    def get_and_encode_image(self):
        with open('images/avatar.jpg', 'rb') as image:
            image_b64 = base64.b64encode(image.read()).decode()
            return "data:image/jpeg;base64," + image_b64
    def create_task(self, image_b64: str):
        url = "https://stablediffusionweb.com/api/generate.image.addTasks?batch=1"
        self.create_task_data['0']['json']['input_image'] = image_b64
        response = requests.request("POST", url, headers=self.headers, data=json.dumps(self.create_task_data))
        return response.json()

    def check_status(self, uuid: str):
        url = "https://stablediffusionweb.com/api/generate.image.getTasks?batch=1"
        self.check_data['0']['json'][0]['uuid'] = uuid
        response = requests.request("POST", url, headers=self.headers, data=json.dumps(self.check_data))
        return response.json()

    def get_image_url(self) -> str:
        image = self.get_and_encode_image()
        task_response = self.create_task(image)
        uuid = task_response[0]['result']['data']['json'][0]['uuid']
        status = ""
        response = None
        while status != "completed":
            response = self.check_status(uuid)
            status = response[0]['result']['data']['json'][0]['status']
            time.sleep(1)
        return response[0]['result']['data']['json'][0]['s3_url']

    def save_image(self):
        url  = self.get_image_url()
        picture_request = requests.get(url)
        if picture_request.status_code == 200:
            with open("images/new_avatar.jpg", 'wb') as f:
                f.write(picture_request.content)


if __name__ == '__main__':
    g = AvatarGenerator()
    g.save_image()



