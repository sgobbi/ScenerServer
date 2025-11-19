from sdk.protobuf import message_pb2
from beartype import beartype
import asyncio


@beartype
class Queue:
    """Manage client queues creation / deletion"""

    def __init__(self):
        self.input: asyncio.Queue[message_pb2.Content] = asyncio.Queue()
        self.output: asyncio.Queue[message_pb2.Content] = asyncio.Queue()

    def clear(self):
        """Clear queues without blocking."""
        while not self.input.empty():
            try:
                self.input.get_nowait()
                self.input.task_done()
            except asyncio.QueueEmpty:
                break
        while not self.output.empty():
            try:
                self.output.get_nowait()
                self.output.task_done()
            except asyncio.QueueEmpty:
                break
