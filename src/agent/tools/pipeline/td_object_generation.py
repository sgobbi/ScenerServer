from beartype import beartype
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent.tools.scene.improver import improve_prompt
from agent.tools.pipeline.image_generation import generate_image_from_prompt
from lib import logger
from library.api import LibraryAPI
from model import trellis

# TODO: modify the tool so that it doesn't reload model on every new request (do we want to do that? cuz it's heavy); add field descriptions for pydantic models


class TDObjectMetaData(BaseModel):
    id: str
    filename: str
    path: str
    error: str | None


class Generate3DObjectOutput(BaseModel):
    text: str
    data: TDObjectMetaData


class Generate3DObjectToolInput(BaseModel):
    user_input: str = Field(description="The raw user's description prompt.")


@beartype
def generate_3d_object_from_prompt(
    library_api: LibraryAPI, prompt: str, id: str | None = None
) -> TDObjectMetaData:
    logger.info(f"Generating 3D object from prompt: {prompt[:10]}...")

    try:
        improved_prompt = improve_prompt(prompt)
    except Exception as e:
        raise

    logger.info("Searching for already existing assets...")

    asset = library_api.find_asset_by_description(improved_prompt)
    if asset.data:
        logger.info(f"Found already existing asset: {asset.data}.")
        return TDObjectMetaData(
            id=asset.data.name,
            filename=f"{asset.data.name}.glb",
            path=asset.data.mesh,
            error=None,
        )
    else:
        logger.info("No existing assets found, generating 3D object.")

        try:
            image_meta_data = generate_image_from_prompt(improved_prompt, id)

            trellis.generate(image_meta_data.path, image_meta_data.id)

            library_api.add_asset(
                image_meta_data.id,
                str(image_meta_data.path),
                str(image_meta_data.path.parent / f"{image_meta_data.id}.glb"),
                description=improved_prompt,
            )

            return TDObjectMetaData(
                id=image_meta_data.id,
                filename=f"{image_meta_data.id}.glb",
                path=str(image_meta_data.path.parent / f"{image_meta_data.id}.glb"),
                error=None,
            )

        except Exception as e:
            logger.error(
                f"Failed to generate 3D object for '{image_meta_data.id}': {e}"
            )
            raise ValueError(
                f"Failed to generate 3D object for '{image_meta_data.id}': {e}"
            )


@tool(args_schema=Generate3DObjectToolInput)
@beartype
def generate_3d_object(library_api: LibraryAPI, user_input: str) -> dict:
    """Generates 3D object from user's prompt"""
    try:
        data = generate_3d_object_from_prompt(library_api, user_input)
        return Generate3DObjectOutput(
            text=f"Generated 3D object for '{user_input}'", data=data
        ).model_dump()
    except Exception:
        raise


if __name__ == "__main__":
    user_input = "big black cat on a table"
    res = generate_3d_object(user_input)
    print(res)
