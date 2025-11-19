import os
import time
import asyncio
import threading
import websockets
from server.api import ServerAPI


async def test_client():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as websocket:
        await websocket.send("send me the image of the lego asset")
        response = await websocket.recv()
        print("Server:", response)


def main():
    asyncio.run(test_client())


if __name__ == "__main__":
    main()
