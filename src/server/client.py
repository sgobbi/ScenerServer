from agent.api import AgentAPI
from sdk.protobuf import message_pb2
from sdk.messages import IOutgoingMessage
from server.io.queue import Queue
from lib import logger
from beartype import beartype
from colorama import Fore
import websockets
import asyncio
import uuid


@beartype
class Client:
    """Manage client and queueing input / ouput messages"""

    # Main function
    def __init__(self, websocket: websockets.ServerConnection, agent: AgentAPI):
        from server.io.input import Input
        from server.io.output import Output

        self.websocket = websocket  # The WebSocket connection object
        self.agent = agent
        self.queue = Queue()
        self.queue_input = Input(self)
        self.queue_output = Output(self)

        self.is_active = True  # State to track if the client is active
        self.disconnection = asyncio.Event()
        self.uid = uuid.uuid1()
        self.task_input = None

    def start(self):
        """Start input/output handlers."""
        logger.info(
            f"Client {self.get_uid()} - connection from {self.websocket.remote_address}"
        )
        self.task_input = asyncio.create_task(self.loop_input())
        self.queue_input.start()
        self.queue_output.start()

    async def send_message(self, message: IOutgoingMessage):
        """Queue a message to be sent to the client."""
        # Queue message
        try:
            proto_message = message.to_proto()
            await self.queue.output.put(proto_message)
        # Manage exceptions
        except asyncio.CancelledError:
            logger.error(
                f"Task was cancelled while sending message to {Fore.GREEN}{self.websocket.remote_address}{Fore.RESET}, message type: {type}"
            )
            raise
        except Exception as e:
            logger.error(
                f"Error queuing message for {Fore.GREEN}{self.websocket.remote_address}{Fore.RESET}: {e}, message type: {type}"
            )

    async def loop_input(self):
        """Queue incoming client messages."""

        while self.is_active:
            # Manage messages
            try:
                async for proto in self.websocket:
                    message = message_pb2.Content()
                    message.ParseFromString(proto)
                    await self.queue.input.put(message)

            # Manage exceptions
            except asyncio.CancelledError:
                logger.error(
                    f"Task cancelled for {Fore.GREEN}{self.websocket.remote_address}{Fore.RESET}"
                )
                break
            except websockets.exceptions.ConnectionClosed as e:
                logger.error(
                    f"Client {Fore.GREEN}{self.websocket.remote_address}{Fore.RESET} disconnected. Reason: {e}"
                )
                break
            except Exception as e:
                logger.error(
                    f"Error with client {Fore.GREEN}{self.websocket.remote_address}{Fore.RESET}: {e}"
                )
                break
            finally:
                await self.close()

    async def close(self):
        """Close the WebSocket connection gracefully."""
        # Init closing
        if not self.is_active:
            return
        self.is_active = False

        # Close client tasks
        tasks_to_cancel = [
            t
            for t in [
                self.task_input,
                self.queue_input.task_loop,
                self.queue_output.task_loop,
            ]
            if t and not t.done()
        ]
        for task in tasks_to_cancel:
            task.cancel()

        # Close client connection
        try:
            await self.websocket.close()
        except Exception as e:
            logger.error(
                f"Error closing websocket connection for {self.websocket.remote_address}: {e}"
            )
        finally:
            self.disconnection.set()
        logger.info(
            f"Client {self.get_uid()} - disconnection from {self.websocket.remote_address}"
        )

        # Close client queues
        self.queue.clear()

    def get_uid(self):
        return str(self.uid)[:6]
