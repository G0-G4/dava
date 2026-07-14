from abc import ABC, abstractmethod

class ImageGenerator(ABC):
    @abstractmethod
    async def generate_and_save_image(self, prompt: str, input_image_path: str, output_path: str) -> str:
        """Generate an image using the given prompt and input (conditioning) image.

        The input_image_path may be the user's raw base avatar or a scene reference image
        (for background stabilization).
        """