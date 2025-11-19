import asyncio

from beartype import beartype

from lib import logger
from server.client import Client
from sdk.messages import OutgoingErrorMessage


@beartype
class Output:
    """Manage client queued ouput messages"""

    # Main function
    def __init__(self, client: Client):
        self.client = client
        self.task_loop = None

    def start(self):
        self.task_loop = asyncio.create_task(self.loop())

    async def loop(self):
        """While client keep being active, handle output messages"""
        while self.client.is_active:
            # Handle client message
            try:
                message = (
                    await self.client.queue.output.get()
                )  # Take the older message of the queue
                await self.handle_message(message)
                self.client.queue.output.task_done()

            # Manage exceptions
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Output error: {e}")
                await self.client.send_error(
                    OutgoingErrorMessage(
                        500, f"Internal server error in thread {self.client.get_uid()}"
                    )
                )
                break

    async def handle_message(self, message):
        """Process the outgoing messages in the client's queue."""
        # Output management
        try:
            logger.info(
                f"Server send message to client {self.client.get_uid()} of type {message.type}"
            )
            await self.client.websocket.send(message.SerializeToString())

        # Manage exceptions
        except asyncio.CancelledError:
            logger.info(
                f"Client {self.client.get_uid()} cancelled for websocket {self.client.websocket.remote_address}"
            )
