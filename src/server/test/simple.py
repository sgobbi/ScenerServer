from server.protobuf import message_pb2
from colorama import Fore
import websockets
import asyncio


async def main():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as ws:
        # Send initial protobuf message
        msg = message_pb2.Content()
        msg.type = "json"
        msg.text = '{"hello":"world"}'
        msg.status = 200
        await ws.send(msg.SerializeToString())

        print("Protobuf message sent.")


asyncio.run(main())
