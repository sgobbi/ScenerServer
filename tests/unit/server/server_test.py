import asyncio
import pytest
import signal
import uuid
import websockets.exceptions

from colorama import Fore, Style
from server.client import Client
from server.session import Session
from server.server import Server
from server.io.valider import InputMessage, OutputMessage
from unittest.mock import AsyncMock, MagicMock, patch, call, Mock


############ MOCK stuff ############


# Pytest fixture that mocks an asynchronous WebSocket connection
@pytest.fixture
def mock_ws():
    ws = AsyncMock()  # Simulates an async WebSocket instance
    ws.remote_address = ("127.0.0.1", 12345)  # Sets a fake remote address
    return ws


# Pytest fixture that mocks an agent with a mock 'achat' method
@pytest.fixture
def mock_agent():
    agent_instance = Mock()  # Creates a general-purpose mock object for the agent
    agent_instance.achat = MagicMock()  # Mocks the 'achat' method on the agent
    return agent_instance


# Pytest fixture that creates a Client using the mocked WebSocket and agent
@pytest.fixture
def mock_client(mock_ws, mock_agent):
    return Client(mock_ws, mock_agent)


# Mock class simulating a WebSocket server for testing
class MockWsServer:
    def __init__(self):
        self.close = Mock()  # Mocks the 'close' method
        self.wait_closed = AsyncMock()  # Mocks the async 'wait_closed' method
        self._is_serving = True  # Simulated internal state flag

    def is_serving(self):
        return self._is_serving  # Returns the mock server's current state


############ test stuff ############
class TestServer:
    def run_coroutine(self, coroutine):
        """Helper method to run async coroutines in sync context"""
        return asyncio.run(coroutine)

    @pytest.fixture
    def mock_logger(self):
        with patch("server.server.logger") as mock_logger:
            yield mock_logger

    @pytest.fixture
    def mock_server(self, mock_agent):
        """Pytest fixture that creates a mocked Server instance with patched dependencies"""
        # Patch AgentAPI to return the mock_agent
        with patch(
            "server.server.AgentAPI", new_callable=Mock, return_value=mock_agent
        ):
            # Patch logger to prevent real logging
            with patch("server.server.logger"):
                server = Server(host="0.0.0.0", port=8765)
                server.handler_shutdown = Mock()  # Mock the shutdown handler method
                return server

    @patch("server.server.AgentAPI")  # Patch AgentAPI for this test
    def test_init_success(self, mock_agent_api, mock_logger, mock_agent):
        """Unit test to check server initialization when AgentAPI initializes correctly"""
        mock_agent_api.return_value = (
            mock_agent  # Configure AgentAPI mock to return mock_agent
        )

        server = Server(host="0.0.0.0", port=8765)

        # Validate server state after init
        assert server.host == "0.0.0.0"
        assert server.port == 8765
        assert server.list_client is not None
        assert server.server is None
        assert server.agent is mock_agent  # Agent should be correctly assigned

        mock_agent_api.assert_called_once()  # Ensure AgentAPI was instantiated once

        # Check that a success message was logged
        mock_logger.info.assert_called_once_with(
            "AgentAPI initialized successfully at server startup."
        )

    @patch("server.server.AgentAPI")
    def test_init_agent_error(self, mock_agent_api, mock_logger):
        """Unit test to check server behavior when AgentAPI initialization fails"""
        err = ValueError("test")
        mock_agent_api.side_effect = err  # Simulate AgentAPI throwing an error

        server = Server(host="0.0.0.0", port=8765)

        # Validate server fallback behavior
        assert server.host == "0.0.0.0"
        assert server.port == 8765
        assert server.list_client is not None
        assert server.server is None
        assert server.agent is None  # Agent should be None due to init failure

        mock_agent_api.assert_called_once()

        # Ensure critical error was logged
        mock_logger.critical.assert_called_once_with(
            f"Failed to initialize AgentAPI at server startup: {err}"
        )

    @patch("server.server.asyncio.get_event_loop")
    def test_start_success(self, mock_get_event_loop, mock_logger, mock_server):
        """Test: successful server start"""

        # Mock coroutine simulating server run
        async def mock_run_server():
            mock_server.server = mock_ws_server
            await asyncio.sleep(0.01)
            mock_ws_server._is_serving = False

        # Setup mocks
        mock_loop = MagicMock()
        mock_get_event_loop.return_value = mock_loop
        mock_ws_server = MockWsServer()
        mock_server.run = AsyncMock(side_effect=mock_run_server)
        mock_loop.run_until_complete.side_effect = self.run_coroutine

        # Run the server start logic
        mock_server.start()

        # Assertions
        mock_server.run.assert_awaited_once()
        mock_get_event_loop.assert_called_once()
        assert mock_loop.run_until_complete.call_count == 2
        mock_loop.add_signal_handler.assert_called_once_with(
            signal.SIGINT, mock_server.handler_shutdown
        )
        mock_server.server.wait_closed.assert_awaited_once()
        mock_logger.info.assert_called_once_with("Server finished working.")

    @patch("server.server.asyncio.get_event_loop")
    def test_start_exception(self, mock_get_event_loop, mock_logger, mock_server):
        mock_loop = MagicMock()
        mock_get_event_loop.return_value = mock_loop
        err = ValueError("test")
        mock_server.run = AsyncMock(side_effect=err)
        mock_server.server = MockWsServer()
        mock_loop.run_until_complete.side_effect = self.run_coroutine

        mock_server.start()

        mock_server.run.assert_awaited_once()

        mock_get_event_loop.assert_called_once()
        mock_loop.add_signal_handler.assert_called_once_with(
            signal.SIGINT, mock_server.handler_shutdown
        )
        assert mock_loop.run_until_complete.call_count == 1

        mock_logger.error.assert_called_once_with(
            f"Error in server's main execution: {err}"
        )

        mock_logger.info.assert_called_once_with("Server finished working.")

    @pytest.mark.asyncio
    @patch("server.server.websockets.serve", new_callable=AsyncMock)
    async def test_run_success(self, mock_ws_serve, mock_logger, mock_server):
        mock_ws_server = MockWsServer()
        mock_ws_serve.return_value = mock_ws_server

        await mock_server.run()

        mock_ws_serve.assert_awaited_once_with(
            mock_server.handler_client, mock_server.host, mock_server.port
        )
        mock_ws_server.wait_closed.assert_awaited_once()

        mock_logger.info.assert_called_once_with(
            f"Server running on {Fore.GREEN}ws://{mock_server.host}:{mock_server.port}{Fore.GREEN}"
        )

    @pytest.mark.asyncio
    @patch("server.server.websockets.serve", new_callable=AsyncMock)
    async def test_run_os_error(self, mock_ws_serve, mock_logger, mock_server):
        err = OSError("test")
        mock_ws_serve.side_effect = err

        await mock_server.run()

        assert mock_server.shutdown_event.is_set()
        mock_ws_serve.assert_awaited_once_with(
            mock_server.handler_client, mock_server.host, mock_server.port
        )

        mock_logger.error.assert_called_once_with(
            f"Could not start server on {Fore.GREEN}ws://{mock_server.host}:{mock_server.port}{Fore.GREEN}: {err}."
        )

    @pytest.mark.asyncio
    @patch("server.server.websockets.serve", new_callable=AsyncMock)
    async def test_run_other_exception(self, mock_ws_serve, mock_logger, mock_server):
        err = ValueError("test")
        mock_ws_serve.side_effect = err

        await mock_server.run()

        assert mock_server.shutdown_event.is_set()
        mock_ws_serve.assert_awaited_once_with(
            mock_server.handler_client, mock_server.host, mock_server.port
        )

        mock_logger.error.assert_called_once_with(
            f"Internal error during server run: {err}"
        )

    async def _mock_disconnection(self, mock_client):
        await asyncio.sleep(0.01)
        mock_client.is_active = False
        mock_client.disconnection.set()

    def _client_instance(self):
        mock_client = MagicMock()
        mock_client.websocket = mock_ws
        mock_client.disconnection = asyncio.Event()
        mock_client.is_active = True
        mock_client.start = Mock()
        mock_client.close = AsyncMock()
        return mock_client

    @pytest.mark.asyncio
    @patch("server.client.Client")
    async def test_handler_client_success(
        self, mock_client_instance, mock_logger, mock_server, mock_ws
    ):
        mock_client = self._client_instance()
        mock_client_instance.return_value = mock_client

        handler_task = asyncio.create_task(mock_server.handler_client(mock_ws))
        disconnection_task = asyncio.create_task(self._mock_disconnection(mock_client))

        await asyncio.gather(handler_task, disconnection_task)

        mock_client_instance.assert_called_once_with(mock_ws, mock_server.agent)
        mock_client.start.assert_called_once()

        assert not mock_server.list_client

        assert mock_logger.info.call_count == 3
        mock_logger.info.assert_any_call(
            f"New client connected:: {mock_ws.remote_address}"
        )
        mock_logger.info.assert_any_call(
            f"Removed client {mock_ws.remote_address} from list. (Remaining: {len(mock_server.list_client)})"
        )
        mock_logger.info.assert_any_call(
            f"Finished closing the client {mock_ws.remote_address}."
        )

    @pytest.mark.asyncio
    @patch("server.client.Client")
    async def test_handler_client_finally_closes_client(
        self, mock_client_instance, mock_logger, mock_server, mock_ws
    ):
        async def mock_failed_disconnection(mock_client):
            await asyncio.sleep(0.01)
            mock_client.disconnection.set()

        mock_client = self._client_instance()
        mock_client_instance.return_value = mock_client

        handler_task = asyncio.create_task(mock_server.handler_client(mock_ws))
        disconnection_task = asyncio.create_task(mock_failed_disconnection(mock_client))

        await asyncio.gather(handler_task, disconnection_task)

        mock_client_instance.assert_called_once_with(mock_ws, mock_server.agent)
        mock_client.start.assert_called_once()

        assert not mock_server.list_client

        assert mock_logger.info.call_count == 2
        mock_logger.info.assert_any_call(
            f"New client connected:: {mock_ws.remote_address}"
        )
        mock_logger.warning.assert_called_once_with(
            f"Client {mock_ws.remote_address} still marked active in finally. Forcing close."
        )

        mock_logger.info.assert_any_call(
            f"Finished closing the client {mock_ws.remote_address}."
        )

    @pytest.mark.asyncio
    @patch("server.client.Client")
    async def test_handler_client_cancelled_error(
        self, mock_client_instance, mock_logger, mock_server, mock_ws
    ):
        mock_client = self._client_instance()
        mock_client.close = AsyncMock(
            side_effect=lambda: setattr(mock_client, "is_active", False)
        )
        mock_client.disconnection.wait = AsyncMock(side_effect=asyncio.CancelledError)
        mock_client_instance.return_value = mock_client

        await mock_server.handler_client(mock_ws)

        mock_client.close.assert_awaited_once()

        assert not mock_server.list_client

        assert mock_logger.info.call_count == 2
        mock_logger.info.assert_any_call(
            f"New client connected:: {mock_ws.remote_address}"
        )
        mock_logger.info.assert_any_call(
            f"Finished closing the client {mock_ws.remote_address}."
        )
        mock_logger.error.assert_called_once_with(
            f"Task cancelled for client {mock_ws.remote_address} disconnection event."
        )

    @pytest.mark.asyncio
    @patch("server.client.Client")
    async def test_handler_client_other_exception(
        self, mock_client_instance, mock_logger, mock_server, mock_ws
    ):
        err = ValueError("test")
        mock_client = self._client_instance()
        mock_client.close = AsyncMock(
            side_effect=lambda: setattr(mock_client, "is_active", False)
        )
        mock_client.disconnection.wait = AsyncMock(side_effect=err)
        mock_client_instance.return_value = mock_client

        await mock_server.handler_client(mock_ws)

        mock_logger.error.assert_called_once_with(
            f"Internal error for client {mock_ws.remote_address} disconnection event: {err}"
        )

        mock_client.close.assert_awaited_once()

        assert not mock_server.list_client

        assert mock_logger.info.call_count == 2
        mock_logger.info.assert_any_call(
            f"New client connected:: {mock_ws.remote_address}"
        )
        mock_logger.info.assert_any_call(
            f"Finished closing the client {mock_ws.remote_address}."
        )

    @pytest.mark.asyncio
    async def test_shutdown_success(self, mock_logger, mock_server):
        mock_client1 = self._client_instance()
        mock_client2 = self._client_instance()
        mock_client3 = self._client_instance()
        mock_client3.is_active = False

        mock_server.list_client = [mock_client1, mock_client2, mock_client3]
        mock_server.server = MockWsServer()

        await mock_server.shutdown()

        mock_server.server.close.assert_called_once()
        mock_server.server.wait_closed.assert_awaited_once()

        mock_client1.close.assert_awaited_once()
        mock_client2.close.assert_awaited_once()

        assert not mock_server.list_client

        assert mock_logger.success.call_count == 2
        mock_logger.success.assert_any_call(f"Server shutdown")
        mock_logger.success.assert_any_call(
            f"Server shutdown sequence completed.{Style.RESET_ALL}"
        )

        mock_logger.info.assert_called_once_with(
            "All client connections processed for shutdown."
        )

    @pytest.mark.asyncio
    async def test_shutdown_cancelled_error(self, mock_logger, mock_server):
        mock_client1 = self._client_instance()
        mock_client2 = self._client_instance()
        mock_client3 = self._client_instance()
        mock_client3.is_active = False

        mock_server.list_client = [mock_client1, mock_client2, mock_client3]
        mock_server.server = MockWsServer()
        mock_server.server.wait_closed = AsyncMock(side_effect=asyncio.CancelledError)

        await mock_server.shutdown()

        mock_server.server.close.assert_called_once()
        mock_server.server.wait_closed.assert_awaited_once()

        mock_client1.close.assert_awaited_once()
        mock_client2.close.assert_awaited_once()

        assert not mock_server.list_client

        mock_logger.error.assert_called_once_with(f"Server shutdown task cancelled")
        mock_logger.success.assert_called_once_with(
            f"Server shutdown sequence completed.{Style.RESET_ALL}"
        )
        mock_logger.info.assert_called_once_with(
            "All client connections processed for shutdown."
        )

    @pytest.mark.asyncio
    async def test_shutdown_other_exception(self, mock_logger, mock_server):
        mock_client1 = self._client_instance()
        mock_client2 = self._client_instance()
        mock_client3 = self._client_instance()
        mock_client3.is_active = False
        err = ValueError("test")

        mock_server.list_client = [mock_client1, mock_client2, mock_client3]
        mock_server.server = MockWsServer()
        mock_server.server.wait_closed = AsyncMock(side_effect=err)

        await mock_server.shutdown()

        mock_server.server.close.assert_called_once()
        mock_server.server.wait_closed.assert_awaited_once()

        mock_client1.close.assert_awaited_once()
        mock_client2.close.assert_awaited_once()

        assert not mock_server.list_client

        mock_logger.error.assert_called_once_with(
            f"Error during server shutdown: {err}"
        )
        mock_logger.success.assert_called_once_with(
            f"Server shutdown sequence completed.{Style.RESET_ALL}"
        )
        mock_logger.info.assert_called_once_with(
            "All client connections processed for shutdown."
        )

    @pytest.mark.asyncio
    async def test_close_client_success(self, mock_server, mock_client):
        mock_client.close = AsyncMock()
        mock_server.list_client = [mock_client]

        await mock_server._close_client(mock_client)

        mock_client.close.assert_awaited_once()

        assert not mock_server.list_client

    @pytest.mark.asyncio
    async def test_close_client_exception_on_client_close(
        self, mock_logger, mock_server, mock_client
    ):
        err = ValueError("test")
        mock_client.close = AsyncMock(side_effect=err)
        mock_client.websocket.close = AsyncMock()
        mock_client.disconnection.set = Mock()
        mock_server.list_client = [mock_client]

        await mock_server._close_client(mock_client)

        mock_client.close.assert_awaited_once()
        mock_client.websocket.close.assert_awaited_once()
        assert not mock_client.is_active
        mock_client.disconnection.set.assert_called_once()

        assert not mock_server.list_client

        mock_logger.error.assert_called_once_with(
            f"Error closing client {mock_client.websocket.remote_address}: {err}"
        )

    @pytest.mark.asyncio
    async def test_close_client_exception_on_ws_close(
        self, mock_logger, mock_server, mock_client
    ):
        err = ValueError("test")
        mock_client.close = AsyncMock(side_effect=err)
        mock_client.websocket.close = AsyncMock(side_effect=err)
        mock_client.disconnection.set = Mock()
        mock_server.list_client = [mock_client]

        await mock_server._close_client(mock_client)

        mock_client.close.assert_awaited_once()
        mock_client.websocket.close.assert_awaited_once()
        assert not mock_client.is_active
        mock_client.disconnection.set.assert_called_once()

        assert not mock_server.list_client

        mock_logger.error.assert_called_once_with(
            f"Error closing client {mock_client.websocket.remote_address}: {err}"
        )
        mock_logger.info.assert_called_once_with(
            f"Failed to close websocket connection for {mock_client.websocket.remote_address}: {err}"
        )
