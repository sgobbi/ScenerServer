from beartype import beartype
from langchain_core.tools import tool
from pathlib import Path
from pydantic import BaseModel, Field
from uuid import uuid4

from agent.tools.scene.improver import improve_prompt
from lib import logger
from model import stable_diffusers


class ImageMetaData(BaseModel):
    id: str
    prompt: str
    filename: str
    path: Path
    error: str | None


class GenerateImageOutput(BaseModel):
    text: str
    data: ImageMetaData


class GenerateImageToolInput(BaseModel):
    user_input: str = Field(description="The raw user's description prompt.")


@beartype
def generate_image_from_prompt(prompt: str, id: str | None = None) -> ImageMetaData:
    if not id:
        id = uuid4()

    logger.info(f"Generating image for '{id}': {prompt[:10]}...")

    output_dir = Path(__file__).resolve().parents[3] / "media" / "temp"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{id}.png"

    try:
        stable_diffusers.generate(prompt, str(output_path))

        return ImageMetaData(
            id=str(id),
            prompt=prompt,
            filename=output_path.name,
            path=output_path,
            error=None,
        )
    except Exception as e:
        logger.error(f"Failed to generate image: {e}")
        raise ValueError(f"Failed to generate image: {e}")


@tool(args_schema=GenerateImageToolInput)
@beartype
def generate_image(user_input: str):
    """Generates an image from user's prompt"""
    try:
        improved_prompt = improve_prompt(user_input)
    except Exception:
        raise

    try:
        data = generate_image_from_prompt(improved_prompt)
        return GenerateImageOutput(
            text=f"Generated image for {user_input}", data=data
        ).model_dump()
    except Exception:
        raise


if __name__ == "__main__":
    user_input = "Big black cat on a table"
    res = generate_image(user_input)
    print(res)
