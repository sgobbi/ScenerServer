from beartype import beartype
from langchain_core.tools import tool
from library.api import LibraryAPI
from pydantic import BaseModel, Field

from agent.tools.scene.decomposer import (
    final_decomposition,
    initial_decomposition,
)
from agent.tools.pipeline.td_object_generation import (
    TDObjectMetaData,
    generate_3d_object_from_prompt,
)
from lib import logger
from sdk.scene import Scene


class Generate3DSceneToolInput(BaseModel):
    user_input: str = Field(description="The raw user's description prompt.")


class Generate3DSceneOutput(BaseModel):
    text: str
    final_decomposition: Scene
    objects_to_send: list[TDObjectMetaData]


@tool(args_schema=Generate3DSceneToolInput)
@beartype
def generate_3d_scene(library_api: LibraryAPI, user_input: str) -> dict:
    """Creates a complete 3D environment or scene with multiple objects or a background."""
    logger.info(f"Generating 3D scene from prompt: {user_input[:10]}...")

    try:
        initial_decomposition_output = initial_decomposition(user_input)
    except Exception:
        raise

    objects_to_send = []

    try:
        for object in initial_decomposition_output.scene.objects:
            if object.type == "dynamic":
                generated_object_meta_data = generate_3d_object_from_prompt(
                    library_api, object.prompt, object.id
                )
                object.id = generated_object_meta_data.id
                objects_to_send.append(generated_object_meta_data)
    except Exception:
        raise

    try:
        final_decomposition_output = final_decomposition(
            user_input, initial_decomposition_output
        )

        return Generate3DSceneOutput(
            text=f"Generated 3D scene for {user_input}",
            final_decomposition=final_decomposition_output.scene,
            objects_to_send=objects_to_send,
        ).model_dump()
    except Exception:
        raise
