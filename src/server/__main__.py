import os

from dotenv import load_dotenv

from server.api import ServerAPI

load_dotenv()

if __name__ == "__main__":
    os.system("clear")
    HOST = os.getenv("WEBSOCKET_HOST", "localhost")
    PORT = int(os.getenv("WEBSOCKET_PORT", 8765))
    server = ServerAPI(host=HOST, port=PORT)
    server.start()
