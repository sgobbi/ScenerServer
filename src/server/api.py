from server.server import Server
import sys


class ServerAPI:
    """API for the WebSocket server."""

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.server = Server(host, port)

    def start(self):
        """Start the WebSocket server."""
        try:
            self.server.start()
        except Exception as e:
            print(f"Error starting server: {e}")
            sys.exit(1)
        finally:
            # self.server.connection.close()
            print("Server stopped.")
