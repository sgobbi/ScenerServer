from sdk.messages import OutgoingErrorMessage
from server.client import Client
from server.data.message import Message
from sdk.protobuf import message_pb2
from lib import logger
from beartype import beartype
import asyncio


@beartype
class Input:
    """Manage client queued input messages"""

    def __init__(self, client: Client):
        self.client = client
        self.message = Message(client)
        self.task_loop = None

    def start(self):
        self.task_loop = asyncio.create_task(self.loop())

    async def loop(self):
        """While client keep being active, handle input messages"""
        while self.client.is_active:
            # Handle client message
            try:
                message = (
                    await self.client.queue.input.get()
                )  # Take the older message of the queue
                await self.handle_message(message)
                self.client.queue.input.task_done()

            # Manage exceptions
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Client input error: {e}")
                await self.client.send_message(
                    OutgoingErrorMessage(
                        500, f"Internal server error in thread {self.client.get_uid()}"
                    )
                )
                break

    async def handle_message(self, msg):
        """handle one client input message - send it to async chat"""
        logger.info(f"Client {self.client.get_uid()} - Received message '{msg.type}'")
        await self.message.handle_incoming_message(msg)
