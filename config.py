import os
from typing import Any, Callable

from dotenv import load_dotenv

def get_variable(name: str, converter: Callable[[str], Any] = str):
    value = converter(os.getenv(name))
    if value is None:
        raise RuntimeError(f"environment value {name} is not set")
    return value

load_dotenv()
PROMPT_TEXT = get_variable("prompt_text")
IMAGE_DIR = get_variable("image_dir")
COOKIES = get_variable("cookies")
PLACE = get_variable("place")
API_ID = get_variable("api_id")
API_HASH = get_variable("api_hash")
LATITUDE = get_variable("latitude", float)
LONGITUDE = get_variable("longitude", float)
TIMEZONE = get_variable("timezone")