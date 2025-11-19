import asyncio
import pytest
import signal
import uuid
import websockets.exceptions

from agent.api import AgentAPI
from colorama import Fore, Style
from server.client import Client
from server.session import Session
from server.server import Server
from server.io.valider import InputMessage, OutputMessage, OutputMessageWrapper
from unittest.mock import AsyncMock, MagicMock, patch, call, Mock

# TODO: fix session, client.loop_input and client.loop_output tests once the pipeline is implemented


############ MOCK stuff ############


# Pytest fixture that mocks an asynchronous WebSocket connection
@pytest.fixture
def mock_ws():
    ws = AsyncMock(
        spec=websockets.ServerConnection
    )  # Simulates an async WebSocket instance
    ws.remote_address = ("127.0.0.1", 12345)  # Sets a fake remote address
    return ws


# Pytest fixture that mocks an agent with a mock 'achat' method
@pytest.fixture
def mock_agent():
    agent_instance = Mock(
        spec=AgentAPI
    )  # Creates a general-purpose mock object for the agent
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

    @patch("server.server.AgentAPI", spec=AgentAPI)  # Patch AgentAPI for this test
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

    @patch("server.server.AgentAPI", spec=AgentAPI)
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
            mock_server.handler_client,
            mock_server.host,
            mock_server.port,
            max_size=10 * 1024 * 1024,
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
            mock_server.handler_client,
            mock_server.host,
            mock_server.port,
            max_size=10 * 1024 * 1024,
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
            mock_server.handler_client,
            mock_server.host,
            mock_server.port,
            max_size=10 * 1024 * 1024,
        )

        mock_logger.error.assert_called_once_with(
            f"Internal error during server run: {err}"
        )

    async def _mock_disconnection(self, mock_client):
        await asyncio.sleep(0.01)
        mock_client.is_active = False
        mock_client.disconnection.set()

    def _client_instance(self):
        mock_client = MagicMock(spec=Client)
        mock_client.websocket = mock_ws
        mock_client.disconnection = asyncio.Event()
        mock_client.is_active = True
        mock_client.start = Mock()
        mock_client.close = AsyncMock()
        return mock_client

    @pytest.mark.asyncio
    @patch("server.client.Client", spec=Client)
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
    @patch("server.client.Client", spec=Client)
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
    @patch("server.client.Client", spec=Client)
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
    @patch("server.client.Client", spec=Client)
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


@pytest.mark.skip
class TestSession:
    async def _mock_achat_gen(self, tokens):
        for token in tokens:
            await asyncio.sleep(0)
            yield token

    @pytest.fixture
    def mock_logger(self):
        with patch("server.session.logger") as mock_logger:
            yield mock_logger

    @pytest.fixture
    def mock_session(self, mock_client):
        with patch("server.session.uuid.uuid1") as mock_uuid1:
            with patch("server.session.logger") as mock_logger:
                mock_uuid1.return_value = uuid.UUID(
                    "11111111-1111-1111-1111-111111111111"
                )
                return Session(mock_client)

    @pytest.mark.asyncio
    async def test_run_success(self, mock_logger, mock_session):

        message1 = InputMessage(command="chat", message="test1")
        message2 = InputMessage(command="chat", message="test2")

        mock_session.client.queue_input.get = AsyncMock(
            side_effect=[
                message1,
                message2,
                asyncio.CancelledError,
            ]
        )
        mock_session.client.queue_input.task_done = MagicMock()

        handle_message_mock = AsyncMock()
        mock_session.handle_message = handle_message_mock
        mock_session.client.is_active = True
        await mock_session.run()

        assert mock_session.client.queue_input.get.await_count == 3
        assert mock_session.client.queue_input.task_done.call_count == 2

        handle_message_mock.assert_has_awaits(
            [
                call(message1),
                call(message2),
            ]
        )

        mock_session.client.queue_input.task_done.assert_called_with()
        assert mock_session.client.queue_input.task_done.call_count == 2
        assert mock_session.handle_message.call_count == 2

        mock_logger.info.assert_called_once_with(
            f"Session {mock_session.thread_id} cancelled for websocket {mock_session.client.websocket.remote_address}"
        )

    @pytest.mark.asyncio
    async def test_run_cancelled_error(self, mock_logger, mock_session):
        mock_session.client.queue_input.get = AsyncMock(
            side_effect=asyncio.CancelledError,
        )
        mock_session.client.queue_input.task_done = AsyncMock()
        handle_message_mock = AsyncMock()
        mock_session.handle_message = handle_message_mock

        await mock_session.run()

        mock_session.handle_message.assert_not_called()
        mock_session.client.queue_input.task_done.assert_not_called()

        mock_logger.info.assert_called_once_with(
            f"Session {mock_session.thread_id} cancelled for websocket {mock_session.client.websocket.remote_address}"
        )

    @pytest.mark.asyncio
    async def test_run_other_exception(self, mock_logger, mock_session):
        err = ValueError("test")
        message = InputMessage(command="chat", message="test")
        mock_session.client.queue_input.get = AsyncMock(
            side_effect=[
                message,
                asyncio.CancelledError(),
            ]
        )
        mock_session.client.queue_input.task_done = AsyncMock()
        mock_session.client.send_message = AsyncMock()

        handle_message_mock = AsyncMock(side_effect=err)
        mock_session.handle_message = handle_message_mock

        await mock_session.run()

        mock_session.client.queue_input.get.assert_awaited_once()
        mock_session.client.queue_input.task_done.assert_not_called()

        handle_message_mock.assert_awaited_once_with(message)

        mock_session.client.send_message.assert_awaited_once_with(
            OutputMessage(
                status="error",
                code=500,
                message=f"Internal server error in thread {mock_session.thread_id}",
            )
        )

        mock_logger.error.assert_called_once_with(f"Session error: {err}")

    @pytest.mark.asyncio
    async def test_handle_message_success(
        self,
        mock_logger,
        mock_session,
    ):
        message = InputMessage(command="chat", message="test test test")
        tokens = ["test ", "has...", "passed"]
        mock_session.client.send_message = AsyncMock()
        mock_session.client.agent.achat.return_value = self._mock_achat_gen(tokens)

        await mock_session.handle_message(message)

        mock_session.client.agent.achat.assert_called_once_with(
            message.message, str(mock_session.thread_id)
        )

        assert mock_session.client.send_message.await_count == len(tokens)
        mock_session.client.send_message.assert_has_awaits(
            [
                call(OutputMessage(status="stream", code=200, message=token))
                for token in tokens
            ],
            any_order=False,
        )

        assert mock_logger.info.call_count == 2
        mock_logger.info.assert_any_call(
            f"Received message in thread {mock_session.thread_id}: {message.message}"
        )
        mock_logger.info.assert_any_call(
            f"Stream completed for thread {mock_session.thread_id}"
        )

    @pytest.mark.asyncio
    async def test_handle_message_achat_cancelled_error(
        self, mock_logger, mock_session
    ):
        message = InputMessage(command="chat", message="test")
        mock_session.client.agent.achat.side_effect = asyncio.CancelledError("oups")
        mock_session.client.send_message = AsyncMock()

        with pytest.raises(asyncio.CancelledError, match="oups"):
            await mock_session.handle_message(message)

        mock_session.client.send_message.assert_not_called()

        assert mock_logger.info.call_count == 2
        mock_logger.info.assert_any_call(
            f"Received message in thread {mock_session.thread_id}: {message.message}"
        )
        mock_logger.info.assert_any_call(
            f"Stream cancelled for thread {mock_session.thread_id} for websocket {mock_session.client.websocket.remote_address}"
        )

    @pytest.mark.asyncio
    async def test_handle_message_achat_other_exception(
        self, mock_logger, mock_session
    ):
        err = ValueError("test")
        message = InputMessage(command="chat", message="test")
        mock_session.client.agent.achat.side_effect = err
        mock_session.client.send_message = AsyncMock()

        await mock_session.handle_message(message)

        mock_session.client.send_message.assert_awaited_once_with(
            OutputMessage(
                status="error",
                code=500,
                message=f"Error during chat stream in thread {mock_session.thread_id}",
            )
        )

        mock_logger.info.assert_called_once_with(
            f"Received message in thread {mock_session.thread_id}: {message.message}"
        )
        mock_logger.error.assert_called_once_with(f"Error during chat stream: {err}")

    @pytest.mark.asyncio
    async def test_handle_message_stream_cancelled_error(
        self, mock_logger, mock_session
    ):
        message = InputMessage(command="chat", message="test test test")
        tokens = ["test ", "has...", "passed"]
        mock_session.client.send_message = AsyncMock(
            side_effect=asyncio.CancelledError("oups")
        )
        mock_session.client.agent.achat.return_value = self._mock_achat_gen(tokens)

        with pytest.raises(asyncio.CancelledError, match="oups"):
            await mock_session.handle_message(message)

        mock_session.client.agent.achat.assert_called_once_with(
            message.message, str(mock_session.thread_id)
        )

        mock_session.client.send_message.assert_awaited_once()

        assert mock_logger.info.call_count == 2
        mock_logger.info.assert_any_call(
            f"Received message in thread {mock_session.thread_id}: {message.message}"
        )
        mock_logger.info.assert_any_call(
            f"Stream cancelled for thread {mock_session.thread_id} for websocket {mock_session.client.websocket.remote_address}"
        )

    @pytest.mark.asyncio
    async def test_handle_message_stream_other_exception(
        self, mock_logger, mock_session
    ):
        message = InputMessage(command="chat", message="test test test")
        tokens = ["test ", "has...", "passed"]
        err = ValueError("oups")
        mock_session.client.send_message = AsyncMock(side_effect=err)
        mock_session.client.agent.achat.return_value = self._mock_achat_gen(tokens)

        with pytest.raises(ValueError, match="oups"):
            await mock_session.handle_message(message)

        mock_session.client.agent.achat.assert_called_once_with(
            message.message, str(mock_session.thread_id)
        )
        assert mock_session.client.send_message.call_count == 2
        mock_session.client.send_message.assert_awaited_with(
            OutputMessage(
                status="error",
                code=500,
                message=f"Error during chat stream in thread {mock_session.thread_id}",
            )
        )

        mock_logger.info.assert_called_once_with(
            f"Received message in thread {mock_session.thread_id}: {message.message}"
        )
        mock_logger.error.assert_called_once_with(f"Error during chat stream: {err}")


class TestClient:
    @pytest.fixture
    def mock_logger(self):
        with patch("server.client.logger") as mock_logger:
            yield mock_logger

    @patch("server.session.Session")
    @pytest.mark.asyncio
    async def test_start_client(self, mock_session, mock_client):
        session_mock = MagicMock()
        mock_session.return_value = session_mock
        session_mock.run = AsyncMock()

        mock_client.start()

        assert mock_client.session is session_mock
        assert mock_client.is_active is True
        assert isinstance(mock_client.queue_input, asyncio.Queue)
        assert isinstance(mock_client.queue_output, asyncio.Queue)
        assert isinstance(mock_client.disconnection, asyncio.Event)
        assert mock_client.task_input is not None
        assert mock_client.task_output is not None
        assert mock_client.task_session is not None

        mock_session.assert_called_once_with(mock_client)
        session_mock.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_success(self, mock_client):
        message = OutputMessageWrapper(
            output_message=OutputMessage(
                status="stream", code=200, action="agent_response", message="test"
            ),
            additional_data=None,
        )
        await mock_client.send_message(message)

        assert not mock_client.queue_output.empty()

        queued_message = await mock_client.queue_output.get()

        assert queued_message == OutputMessageWrapper(
            output_message=OutputMessage(
                status="stream", code=200, action="agent_response", message="test"
            ),
            additional_data=None,
        )

    @pytest.mark.asyncio
    async def test_send_message_cancelled_error(self, mock_logger, mock_client):
        mock_client.queue_output.put = AsyncMock(
            side_effect=asyncio.CancelledError("test")
        )
        message = OutputMessageWrapper(
            output_message=OutputMessage(
                status="stream", code=200, action="agent_response", message="test"
            ),
            additional_data=None,
        )

        with pytest.raises(asyncio.CancelledError, match="test"):
            await mock_client.send_message(message)

        mock_client.queue_output.put.assert_awaited_once_with(message)
        mock_logger.error.assert_called_once_with(
            f"Task was cancelled while sending message to {Fore.GREEN}{mock_client.websocket.remote_address}{Fore.RESET}, initial message: {message}"
        )

    @pytest.mark.asyncio
    async def test_send_message_other_exception(
        self, mock_logger, mock_ws, mock_client
    ):
        err = ValueError("error")
        mock_client.queue_output.put = AsyncMock(side_effect=err)
        message = OutputMessageWrapper(
            output_message=OutputMessage(
                status="stream", code=200, action="agent_response", message="test"
            ),
            additional_data=None,
        )

        await mock_client.send_message(message)

        mock_client.queue_output.put.assert_awaited_once_with(message)

        mock_logger.error.assert_called_once_with(
            f"Error queuing message for {Fore.GREEN}{mock_ws.remote_address}{Fore.RESET}: {err}, initial message: {message}"
        )

    @pytest.mark.skip
    @pytest.mark.asyncio
    @patch("server.client.Client.close", new_callable=AsyncMock)
    async def test_loop_input_success(
        self,
        mock_close,
        mock_client,
        mock_logger,
        mock_ws,
    ):
        mock_ws.__aiter__.return_value = ["test1", "test2"]

        async def close_side_effect():
            mock_client.is_active = False

        mock_close.side_effect = close_side_effect
        mock_client.is_active = True

        await mock_client.loop_input()

        mock_close.assert_awaited_once()
        mock_logger.error.assert_not_called()

        queued_messages = []
        while not mock_client.queue_input.empty():
            item = await asyncio.wait_for(mock_client.queue_input.get(), timeout=0.1)
            queued_messages.append(item)
            mock_client.queue_input.task_done()

        assert queued_messages == [
            InputMessage(command="chat", message="test1"),
            InputMessage(command="chat", message="test2"),
        ]

    @pytest.mark.asyncio
    async def test_loop_input_empty_message(self, mock_logger, mock_client, mock_ws):
        mock_ws.__aiter__.return_value = [""]
        mock_client.queue_input.put = AsyncMock()
        mock_client.send_message = AsyncMock()

        await mock_client.loop_input()

        mock_client.queue_input.put.assert_not_awaited()
        mock_client.send_message.assert_awaited_once()

        error_message = mock_client.send_message.await_args.args[0]
        assert isinstance(error_message, OutputMessageWrapper)
        assert error_message.output_message.status == "error"
        assert error_message.output_message.code == 400
        assert "Invalid input" in error_message.output_message.message

        assert mock_client.is_active is False

        mock_logger.error.assert_called_once()
        log_message = mock_logger.error.call_args[0][0]
        assert (
            f"Validation error for client {mock_client.websocket.remote_address}:"
            in log_message
        )

    @pytest.mark.skip
    @pytest.mark.asyncio
    async def test_loop_input_cancelled_error(self, mock_logger, mock_client, mock_ws):
        mock_ws.__aiter__.return_value = ["test"]
        mock_client.queue_input.put = AsyncMock(side_effect=asyncio.CancelledError)

        await mock_client.loop_input()

        mock_client.queue_input.put.assert_awaited_once()
        assert mock_client.queue_input.empty()
        assert mock_client.is_active is False

        mock_logger.error.assert_called_once_with(
            f"Task cancelled for {Fore.GREEN}{mock_ws.remote_address}{Fore.RESET}"
        )

    @pytest.mark.asyncio
    async def test_loop_input_connection_closed(
        self, mock_logger, mock_client, mock_ws
    ):
        # mock_ws.__aiter__ = MagicMock(return_value=mock_ws)
        err = websockets.exceptions.ConnectionClosed(rcvd=None, sent=None)
        # mock_ws.__anext__.side_effect = err
        mock_ws.__aiter__.side_effect = err

        await mock_client.loop_input()

        assert mock_client.queue_input.empty()
        assert mock_client.is_active is False

        mock_logger.error.assert_called_once_with(
            f"Client {Fore.GREEN}{mock_ws.remote_address}{Fore.RESET} disconnected. Reason: {err}"
        )

    @pytest.mark.asyncio
    async def test_loop_input_other_exception(self, mock_logger, mock_client, mock_ws):
        err = ValueError("test")
        mock_ws.__aiter__.side_effect = err
        # = MagicMock(return_value=mock_ws)
        # mock_ws.__anext__.side_effect = err

        await mock_client.loop_input()

        assert mock_client.queue_input.empty()
        assert mock_client.is_active is False

        mock_logger.error.assert_called_once_with(
            f"Error with client {Fore.GREEN}{mock_ws.remote_address}{Fore.RESET}: {err}"
        )

    @pytest.mark.skip
    @pytest.mark.asyncio
    async def test_loop_output_success(self, mock_logger, mock_client, mock_ws):
        message = OutputMessage(status="stream", code=200, message="test")
        mock_client.queue_output.get = AsyncMock(
            side_effect=[message, ValueError("test")]
        )

        await mock_client.loop_output()

        mock_ws.send.assert_awaited_once_with(message.message)

        mock_logger.info.assert_called_once_with(
            f"Sent message to {Fore.GREEN}{mock_ws.remote_address}{Fore.RESET}:\n {message}"
        )

    @pytest.mark.asyncio
    async def test_loop_output_cancelled_error(self, mock_logger, mock_client, mock_ws):
        mock_client.queue_output.get = AsyncMock(side_effect=asyncio.CancelledError)

        await mock_client.loop_output()

        mock_client.queue_output.get.assert_awaited_once()

        mock_ws.send.assert_not_awaited()

        mock_logger.info.assert_called_once_with(
            f"Task cancelled for {Fore.GREEN}{mock_ws.remote_address}{Fore.RESET}"
        )

    @pytest.mark.asyncio
    async def test_loop_output_other_exception_on_get(
        self, mock_logger, mock_client, mock_ws
    ):
        err = ValueError("get_error")
        mock_client.queue_output.get = AsyncMock(side_effect=err)

        await mock_client.loop_output()

        mock_client.queue_output.get.assert_awaited_once()

        mock_ws.send.assert_not_awaited()

        mock_logger.error.assert_called_once_with(
            f"Error sending message to {Fore.GREEN}{mock_ws.remote_address}{Fore.RESET}: {err}"
        )

    @pytest.mark.asyncio
    async def test_loop_output_other_exception_on_send(
        self, mock_logger, mock_client, mock_ws
    ):
        message = OutputMessageWrapper(
            output_message=OutputMessage(
                status="stream", code=200, action="agent_response", message="test"
            ),
            additional_data=None,
        )
        mock_client.queue_output.get = AsyncMock(
            side_effect=[message, asyncio.CancelledError]
        )
        err = ValueError("send_error")
        mock_ws.send.side_effect = err

        await mock_client.loop_output()

        mock_client.queue_output.get.assert_awaited_once()
        assert mock_client.is_active is False

        mock_ws.send.assert_awaited_once_with(message.output_message.model_dump_json())

        mock_logger.error.assert_called_once_with(
            f"Error sending message to {Fore.GREEN}{mock_ws.remote_address}{Fore.RESET}: {err}"
        )

    @pytest.mark.asyncio
    async def test_close_success(self, mock_logger, mock_client, mock_ws):
        mock_client.task_input = asyncio.create_task(asyncio.sleep(1))
        mock_client.task_output = asyncio.create_task(asyncio.sleep(1))
        mock_client.task_session = asyncio.create_task(asyncio.sleep(1))
        mock_client.disconnection = MagicMock(spec=asyncio.Event)

        await mock_client.queue_input.put(InputMessage(command="chat", message="test"))
        await mock_client.queue_output.put(
            OutputMessageWrapper(
                output_message=OutputMessage(
                    status="stream", code=123, action="agent_response", message="test"
                ),
                additional_data=None,
            )
        )

        await mock_client.close()

        assert not mock_client.is_active
        mock_ws.close.assert_awaited_once()
        assert mock_client.queue_input.empty()
        assert mock_client.queue_output.empty()

        mock_client.disconnection.set.assert_called_once()

        mock_logger.info.assert_called_once_with(
            f"Closing connection for {mock_ws.remote_address}"
        )

    @pytest.mark.asyncio
    async def test_close_ws_error(self, mock_logger, mock_client, mock_ws):
        mock_client.task_input = asyncio.create_task(asyncio.sleep(1))
        mock_client.task_output = asyncio.create_task(asyncio.sleep(1))
        mock_client.task_session = asyncio.create_task(asyncio.sleep(1))
        mock_client.disconnection = MagicMock(spec=asyncio.Event)

        err = websockets.exceptions.ConnectionClosed(rcvd=None, sent=None)
        mock_ws.close.side_effect = err

        await mock_client.queue_input.put(InputMessage(command="chat", message="test"))
        await mock_client.queue_output.put(
            OutputMessageWrapper(
                output_message=OutputMessage(
                    status="stream", code=123, action="agent_response", message="test"
                ),
                additional_data=None,
            )
        )

        await mock_client.close()

        assert not mock_client.is_active
        mock_ws.close.assert_awaited_once()
        assert mock_client.queue_input.empty()
        assert mock_client.queue_output.empty()

        mock_client.disconnection.set.assert_called_once()

        mock_logger.info.assert_called_once_with(
            f"Closing connection for {mock_ws.remote_address}"
        )
        mock_logger.error.assert_called_once_with(
            f"Error closing websocket connection for {mock_ws.remote_address}: {err}"
        )
