import os
from lib import speech_to_text
from server.client import Client
from lib import logger
from beartype import beartype
import asyncio
import uuid
import json
from sdk.protobuf import message_pb2
from sdk.messages import *


# Peut etre faudra til mettre chacune des data processing dans des classes distincts


@beartype
class Message:
    """Manage client queued input messages"""

    def __init__(self, client: Client):
        self.client = client

    async def handle_incoming_message(self, proto_message: message_pb2.Content):
        """Process incoming message according to his type"""
        message = IIncomingMessage.from_proto(proto_message)

        match message:
            case IncomingTextMessage():
                await self.handle_text_message(message.text)
            case IncomingAudioMessage():
                await self.handle_audio_message(message.data)
            case IncomingGestureMessage():
                await self.handle_gesture_message(message.data)

    async def handle_text_message(self, message: str):
        """Manage text message"""
        try:
            output_generator = self.client.agent.aask(message, str(self.client.uid))
            async for token in output_generator:
                logger.info(
                    f"Received token for client {self.client.get_uid()}: {token}"
                )
                await self.client.send_message(token)

            logger.info(f"Stream completed for client {self.client.get_uid()}")

        # Manage exceptions
        except asyncio.CancelledError:
            logger.info(
                f"Stream cancelled for client {self.client.get_uid()} for websocket {self.client.websocket.remote_address}"
            )
            raise
        except Exception as e:
            logger.error(f"Error during chat stream: {e}")
            await self.client.send_message(
                OutgoingErrorMessage(
                    status=500,
                    text=f"Error during chat stream in thread {self.client.uid}: {e}",
                )
            )

    async def handle_audio_message(self, data):
        """Manage audio message"""
        os.makedirs("media/temp_audio", exist_ok=True)
        temp_audio_filename = f"media/temp_audio/temp_audio_{uuid.uuid4().hex}.wav"

        with open(temp_audio_filename, "wb") as f:
            f.write(data)

        text = speech_to_text(temp_audio_filename)
        await self.client.send_message(
            OutgoingConvertedSpeechMessage(
                text=text,
            )
        )
        await self.handle_text_message(text)

    async def handle_gesture_message(self, message):
        """Manage gesture message"""
        # TODO: Not implemented yet
        pass
