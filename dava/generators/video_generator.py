from abc import ABC, abstractmethod


class VideoGenerator(ABC):
    @abstractmethod
    async def generate_and_save_video(
        self, prompt: str, reference_image_path: str, output_path: str
    ) -> str: ...