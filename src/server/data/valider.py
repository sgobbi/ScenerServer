import json

from pydantic import BaseModel, field_validator
from typing import Literal

# Encore valide ?


def validate_message(msg):
    """Check message non-emptyness"""
    if not msg or msg.isspace():
        raise ValueError("Message must not be empty or whitespace")
    return msg


class OutputMessage(BaseModel):
    status: Literal["stream", "error"]
    code: int
    action: Literal[
        "agent_response",
        "image_generation",
        "scene_generation",
        "3d_object_generation",
        "thinking_process",
        "converted_speech",
        "unknown_action",
    ]
    message: str
    _validate_message = field_validator("message")(validate_message)


class OutputMessageWrapper(BaseModel):
    output_message: OutputMessage
    additional_data: list[bytes] | dict | None = None


class InputMessageMeta(BaseModel):
    command: Literal["chat"]
    type: Literal["text", "audio"]


class InputMessage(BaseModel):
    command: Literal["chat"]
    message: str

    _validate_message = field_validator("message")(validate_message)


# Main function
async def check_message(client, message):
    """Handle the incoming message and return the response."""
    # Check validity
    if not message:
        await client.send_error(400, "Empty message received")
        return False

    if not is_json(message):
        await client.send_error(400, "Message not in JSON format")
        return False

    if not has_command(message):
        await client.send_error(400, "No command in the json")
        return False

    # Message is valid
    return True


# Subfunction
def is_json(message):
    """Check if the message is a valid JSON."""
    try:
        json.loads(message)  # Try to parse the message as JSON
        return True
    except json.JSONDecodeError:
        return False


def has_command(message):
    """Check if the message contains a 'command' field."""
    try:
        j = json.loads(message)  # Parse the JSON
        if "command" in j:
            return True
        else:
            return False
    except json.JSONDecodeError:
        return False
