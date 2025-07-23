import os
from dotenv import load_dotenv

def get_variable(name: str):
    value = os.getenv(name)
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
