import json

from colorama import Fore
from langchain.callbacks.base import BaseCallbackHandler
from langchain_core.messages import ToolMessage
from loguru import logger


from agent.tools.pipeline.image_generation import GenerateImageOutput
from agent.tools.pipeline.td_object_generation import Generate3DObjectOutput
from agent.tools.pipeline.td_scene_generation import Generate3DSceneOutput
from agent.tools.pipeline.td_scene_modification import Modify3DSceneOutput
from sdk.messages import (
    OutgoingUnrelatedMessage,
    OutgoingConvertedSpeechMessage,
    OutgoingGenerated3DObjectsMessage,
    OutgoingGeneratedImagesMessage,
    OutgoingGenerated3DSceneMessage,
    OutgoingModified3DSceneMessage,
    OutgoingErrorMessage,
    AppMediaAsset,
)
from model.trellis import read_glb


""" Custom tool tracker for functionnal tests """


class Tool_callback(BaseCallbackHandler):
    def __init__(self):
        self.used_tools = []
        self.structured_response: (
            OutgoingConvertedSpeechMessage
            | OutgoingGenerated3DObjectsMessage
            | OutgoingGeneratedImagesMessage
            | OutgoingGenerated3DSceneMessage
            | OutgoingModified3DSceneMessage
            | OutgoingErrorMessage
            | OutgoingUnrelatedMessage
        ) = None

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:
        """Start when a tool is being to be used"""

        # Log starting tool
        tool_name = serialized.get("name")
        logger.info(
            f"Using tool {Fore.GREEN}{tool_name}{Fore.RESET} with input {input_str}"
        )

        # Store used tool names
        if tool_name and tool_name not in self.used_tools:
            self.used_tools.append(tool_name)

    def on_tool_end(self, output: ToolMessage, **kwargs) -> None:
        """Starts when a tool finishes, puts the result in the queue for further processing."""
        tool_name = kwargs.get("name")

        if tool_name == "clear_database" or tool_name == "delete_asset":
            logger.info(f"Tool '{tool_name}' completed with output: {output.content}")
            self.structured_response = OutgoingUnrelatedMessage(text=output.content)
            return

        tool_output = json.loads(output.content)

        match tool_name:
            case "generate_3d_object":
                payload = Generate3DObjectOutput(**tool_output)
                self.structured_response = OutgoingGenerated3DObjectsMessage(
                    text=payload.text,
                    assets=[
                        AppMediaAsset(
                            id=payload.data.id,
                            filename=payload.data.filename,
                            data=read_glb(payload.data.path),
                        )
                    ],
                )
            case "generate_3d_scene":
                payload = Generate3DSceneOutput(**tool_output)
                self.structured_response = OutgoingGenerated3DSceneMessage(
                    text=payload.text,
                    json_scene=payload.final_decomposition.model_dump(),
                    assets=[
                        AppMediaAsset(
                            id=asset_meta_data.id,
                            filename=asset_meta_data.filename,
                            data=read_glb(asset_meta_data.path),
                        )
                        for asset_meta_data in payload.objects_to_send
                    ],
                )
            case "modify_3d_scene":
                payload = Modify3DSceneOutput(**tool_output)
                self.structured_response = OutgoingModified3DSceneMessage(
                    text=payload.text,
                    modified_scene=payload.modified_scene.model_dump(),
                    assets=[
                        AppMediaAsset(
                            id=asset_meta_data.id,
                            filename=asset_meta_data.filename,
                            data=read_glb(asset_meta_data.path),
                        )
                        for asset_meta_data in payload.objects_to_send
                    ],
                )

    def on_tool_error(self, error: BaseException, **kwargs) -> None:
        tool_name = kwargs.get("name")
        logger.error(f"Tool '{tool_name}' encountered an error: {error}")
        self.structured_response = OutgoingErrorMessage(
            status=500, text=f"Internal error, please try again."
        )
