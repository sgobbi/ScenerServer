from server.protobuf import message_pb2
import websockets
import asyncio


async def main():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as ws:
        # Load image as bytes
        with open("src/server/test/image.png", "rb") as f:
            image_bytes = f.read()

        # Create protobuf message
        msg = message_pb2.Content()
        msg.type = "image"
        msg.data = image_bytes
        msg.status = 200

        await ws.send(msg.SerializeToString())
        print("Protobuf image message sent.")


asyncio.run(main())
