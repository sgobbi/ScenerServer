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
from websockets.asyncio.server import ServerConnection
from agent.api import AgentAPI


# =================
# MOCK stuff
# =================
# Pytest fixture that mocks an asynchronous WebSocket connection
@pytest.fixture
def mock_ws():
    ws = AsyncMock(spec=ServerConnection)  # Simulates an async WebSocket instance
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


# =================
# TEST stuff
# =================
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
        message = OutputMessage(status="stream", code=200, message="test")
        await mock_client.send_message(message)

        assert not mock_client.queue_output.empty()

        queued_message = await mock_client.queue_output.get()

        assert queued_message == OutputMessage(
            status="stream", code=200, message="test"
        )

    @pytest.mark.asyncio
    async def test_send_message_cancelled_error(self, mock_logger, mock_client):
        mock_client.queue_output.put = AsyncMock(
            side_effect=asyncio.CancelledError("test")
        )
        message = OutputMessage(status="stream", code=200, message="test")

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
        message = OutputMessage(status="stream", code=200, message="test")

        await mock_client.send_message(message)

        mock_client.queue_output.put.assert_awaited_once_with(message)

        mock_logger.error.assert_called_once_with(
            f"Error queuing message for {Fore.GREEN}{mock_ws.remote_address}{Fore.RESET}: {err}, initial message: {message}"
        )

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
        assert isinstance(error_message, OutputMessage)
        assert error_message.status == "error"
        assert error_message.code == 400
        assert "Invalid input" in error_message.message

        assert mock_client.is_active is False

        mock_logger.error.assert_called_once()
        log_message = mock_logger.error.call_args[0][0]
        assert (
            f"Validation error for client {mock_client.websocket.remote_address}:"
            in log_message
        )

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
        mock_ws.__aiter__ = MagicMock(return_value=mock_ws)
        err = websockets.exceptions.ConnectionClosed(rcvd=None, sent=None)
        mock_ws.__anext__.side_effect = err

        await mock_client.loop_input()

        assert mock_client.queue_input.empty()
        assert mock_client.is_active is False

        mock_logger.error.assert_called_once_with(
            f"Client {Fore.GREEN}{mock_ws.remote_address}{Fore.RESET} disconnected. Reason: {err}"
        )

    @pytest.mark.asyncio
    async def test_loop_input_other_exception(self, mock_logger, mock_client, mock_ws):
        err = ValueError("test")
        mock_ws.__aiter__ = MagicMock(return_value=mock_ws)
        mock_ws.__anext__.side_effect = err

        await mock_client.loop_input()

        assert mock_client.queue_input.empty()
        assert mock_client.is_active is False

        mock_logger.error.assert_called_once_with(
            f"Error with client {Fore.GREEN}{mock_ws.remote_address}{Fore.RESET}: {err}"
        )

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
        message = OutputMessage(status="stream", code=200, message="test")
        mock_client.queue_output.get = AsyncMock(
            side_effect=[message, asyncio.CancelledError]
        )
        err = ValueError("send_error")
        mock_ws.send.side_effect = err

        await mock_client.loop_output()

        mock_client.queue_output.get.assert_awaited_once()
        assert mock_client.is_active is False

        mock_ws.send.assert_awaited_once_with(message.message)

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
            OutputMessage(status="stream", code=123, message="test")
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
            OutputMessage(status="stream", code=123, message="test")
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
