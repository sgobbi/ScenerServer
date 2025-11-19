import asyncio
import uuid
from beartype import beartype
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from library.api import LibraryAPI
from pydantic import BaseModel, Field

from agent.tools.scene.analyzer import SceneUpdate, analyze
from agent.tools.pipeline.td_object_generation import (
    TDObjectMetaData,
    generate_3d_object_from_prompt,
)
from lib import logger
from sdk.scene import Scene
from server.data.redis import Redis


class Modify3DSceneToolInput(BaseModel):
    user_input: str = Field(description="The raw user's modification request.")


class Modify3DSceneOutput(BaseModel):
    text: str
    modified_scene: SceneUpdate
    objects_to_send: list[TDObjectMetaData]


@beartype
async def modify_3d_scene_async(
    redis_api: Redis,
    library_api: LibraryAPI,
    user_input: str,
    thread_id: str,
) -> dict:
    """Creates a complete 3D environment or scene with multiple objects or a background."""
    logger.info(f"Modifying 3D scene from prompt: {user_input}...")

    current_scene_json = await redis_api.get_scene(thread_id)
    validated_current_scene = Scene.model_validate_json(current_scene_json)
    logger.info(f"Current scene JSON: {validated_current_scene}...")

    try:
        analysis_output = analyze(user_input, validated_current_scene)
    except Exception:
        raise

    objects_to_send = []

    for object in analysis_output.objects_to_add:
        new_id = str(uuid.uuid4())
        object.scene_object.id = new_id

        for component in object.scene_object.components:
            if component.component_type == "dynamic":
                component.id = new_id

        if any(
            component.component_type == "dynamic"
            for component in object.scene_object.components
        ):
            try:
                generated_object_meta_data = generate_3d_object_from_prompt(
                    library_api, object.prompt, object.scene_object.id
                )
                object.scene_object.id = generated_object_meta_data.id
                for component in object.scene_object.components:
                    if component.component_type == "dynamic":
                        component.id = generated_object_meta_data.id
                objects_to_send.append(generated_object_meta_data)
            except Exception:
                raise

    try:
        for object in analysis_output.objects_to_regenerate:
            id = uuid.uuid4()
            generated_object_meta_data = generate_3d_object_from_prompt(
                library_api, object.prompt, str(id)
            )
            object.new_id = generated_object_meta_data.id
            objects_to_send.append(generated_object_meta_data)
    except Exception:
        raise

    return Modify3DSceneOutput(
        text=f"Scene modification for {user_input}",
        modified_scene=analysis_output,
        objects_to_send=objects_to_send,
    ).model_dump()


@tool(args_schema=Modify3DSceneToolInput)
@beartype
def modify_3d_scene(
    redis_api: Redis,
    library_api: LibraryAPI,
    main_loop: asyncio.AbstractEventLoop,
    user_input: str,
    *,
    config: RunnableConfig,
) -> dict:
    """Creates a complete 3D environment or scene with multiple objects or a background."""
    thread_id = config.get("configurable", {}).get("thread_id")

    coro = modify_3d_scene_async(
        redis_api=redis_api,
        library_api=library_api,
        user_input=user_input,
        thread_id=thread_id,
    )

    future = asyncio.run_coroutine_threadsafe(coro, main_loop)

    try:
        result = future.result()
        return result
    except Exception:
        raise
