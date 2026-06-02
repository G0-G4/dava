from abc import ABC, abstractmethod

class ImageGenerator(ABC):
    @abstractmethod
    async def generate_and_save_image(self, prompt: str, base_image_path: str) -> str:
        ...