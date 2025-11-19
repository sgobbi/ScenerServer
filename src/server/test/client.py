from server.protobuf import message_pb2
from colorama import Fore
import websockets
import asyncio


async def main():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as ws:
        loop = asyncio.get_event_loop()

        async def send_loop():
            while True:
                line = await loop.run_in_executor(None, input, "> ")
                if line.lower() in {"exit", "quit"}:
                    await ws.close()
                    break

                msg = message_pb2.Content()
                msg.type = "chat"
                msg.text = f'{{"user":"{line}"}}'
                msg.status = 200

                await ws.send(msg.SerializeToString())
                print(f"{Fore.GREEN}{'Message sent'}{Fore.RESET} \n")

        async def recv_loop():
            while True:
                try:
                    data = await ws.recv()
                    msg = message_pb2.Content()
                    msg.ParseFromString(data)
                    print(f"{Fore.GREEN}{'Response'}{Fore.RESET}: {msg.text} \n")
                except websockets.exceptions.ConnectionClosed:
                    break

        await asyncio.gather(send_loop(), recv_loop())


asyncio.run(main())
