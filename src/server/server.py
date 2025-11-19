import sys
from agent.api import AgentAPI
from library.api import LibraryAPI
from sdk.messages import OutgoingSessionStartMessage
from server.client import Client
from lib import logger
from beartype import beartype
from colorama import Fore, Style
from server.data.redis import Redis
import websockets
import asyncio
import signal

# TODO: cancel agent task if client disconnects


@beartype
class Server:
    """Manage server start / stop and handle clients"""

    # Main function
    def __init__(self, host: str, port: int):
        """Initialize server parameters"""
        self.host = host
        self.port = port
        self.list_client: list[Client] = []
        self.shutdown_event = asyncio.Event()
        self.server = None
        self.agent = None
        self.redis_api = None
        self.library_api = None

    def start(self):
        # Add stopping event
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self.handler_shutdown)

        try:
            # Initialize Redis connection
            self.redis_api = Redis()
            logger.info("Redis connection established successfully.")

            # Initialize Library API
            self.library_api = LibraryAPI()
            logger.info("LibraryAPI initialized successfully.")
        except Exception as e:
            logger.critical(f"Failed to initialize Redis or LibraryAPI: {e}")
            sys.exit(1)

        # Initiate agent
        try:
            self.agent = AgentAPI(self.redis_api, self.library_api, loop)
            logger.info("AgentAPI initialized successfully at server startup.")
        except Exception as e:
            # Shutdown the server if agent init failed?
            logger.critical(f"Failed to initialize AgentAPI at server startup: {e}")
            sys.exit(1)

        # Run into async thread
        try:
            loop.run_until_complete(self.run())
        except Exception as e:
            logger.error(f"Error in server's main execution: {e}")
        finally:
            if self.server is not None and self.server.is_serving():
                loop.run_until_complete(self.server.wait_closed())
            logger.info("Server finished working.")

    # Subfunction
    def handler_shutdown(self):
        """Triggered by SIGINT to start shutdown"""
        asyncio.create_task(self.shutdown())

    async def run(self):
        """Run the WebSocket server."""
        try:
            await self.redis_api.connect()

            # Start serveur and wait to close
            self.server = await websockets.serve(
                self.handler_client, "0.0.0.0", self.port, max_size=10 * 1024 * 1024
            )
            logger.info(
                f"Server running on {Fore.GREEN}ws://{self.host}:{self.port}{Fore.GREEN}"
            )
            print("---------------------------------------------")
            await self.server.wait_closed()

            # Manage exceptions
        except OSError as e:
            logger.error(
                f"Could not start server on {Fore.GREEN}ws://{self.host}:{self.port}{Fore.GREEN}: {e}."
            )
            self.shutdown_event.set()
        except Exception as e:
            print(str(e))
            logger.error(f"Internal error during server run: {e}")
            self.shutdown_event.set()

    async def handler_client(self, websocket: websockets.ServerConnection):
        """Handle an incoming WebSocket client connection."""

        from server.client import Client

        client = None
        try:
            # Create client and run it
            client = Client(websocket, self.agent)
            client.start()
            await client.send_message(OutgoingSessionStartMessage(str(client.uid)))

            self.list_client.append(client)

            # Manage exceptions
            try:
                await client.disconnection.wait()
            except asyncio.CancelledError:
                logger.error(
                    f"Task cancelled for client {websocket.remote_address} disconnection event."
                )
                if client.is_active:
                    await self.remove_client(client)
            except Exception as e:
                logger.error(
                    f"Internal error for client {websocket.remote_address} disconnection event: {e}"
                )
                if client.is_active:
                    await self.remove_client(client)
        finally:
            if client:
                if client.is_active:
                    logger.warning(
                        f"Client {websocket.remote_address} still marked active in finally. Forcing close."
                    )
                    await self.remove_client(client)
                elif client in self.list_client:
                    self.list_client.remove(client)

    async def shutdown(self):
        """Gracefully shut down the server."""
        if self.server:
            self.server.close()
            try:
                print("hello")
                await self.server.wait_closed()
                print("hello")
                print("---------------------------------------------")
                logger.success(f"Server shutdown")
            except asyncio.CancelledError:
                logger.error(f"Server shutdown task cancelled")
            except Exception as e:
                logger.error(f"Error during server shutdown: {e}")

        for client in list(self.list_client):
            if client.is_active:
                await self.remove_client(client)

        self.list_client.clear()

        logger.info("All client connections processed for shutdown.")
        print("---------------------------------------------")
        logger.success(f"Server shutdown sequence completed.{Style.RESET_ALL}")

    async def remove_client(self, client: Client):
        try:
            if client.is_active:
                await client.close()
        except Exception as e:
            logger.error(
                f"Error closing client {client.websocket.remote_address}: {e}",
            )
            try:
                await client.websocket.close()
            except Exception as e:
                logger.info(
                    f"Failed to close websocket connection for {client.websocket.remote_address}: {e}"
                )
            client.is_active = False
            client.disconnection.set()
        finally:
            if client in self.list_client:
                self.list_client.remove(client)
