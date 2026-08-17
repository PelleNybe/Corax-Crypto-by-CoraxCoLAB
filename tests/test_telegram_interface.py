import pytest
from unittest.mock import AsyncMock, MagicMock
from ui.telegram_interface import CoraxTelegramInterface


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    return engine


@pytest.mark.asyncio
async def test_telegram_unauthorized_user(mock_engine, mocker):
    mocker.patch("core.config.settings.TELEGRAM_CHAT_ID", "12345")
    mocker.patch(
        "core.config.settings.TELEGRAM_BOT_TOKEN",
        "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
    )

    interface = CoraxTelegramInterface(mock_engine)

    # Mock message from unauthorized user
    mock_message = AsyncMock()
    mock_message.from_user = MagicMock()
    mock_message.chat = MagicMock()
    mock_message.from_user.id = 99999
    mock_message.chat.id = 12345
    mock_message.text = "Hello"

    handlers = interface.dp.message.handlers
    handle_message = handlers[1].callback

    await handle_message(mock_message)

    # Verify reply was not called because user is unauthorized
    mock_message.reply.assert_not_called()


@pytest.mark.asyncio
async def test_telegram_authorized_user(mock_engine, mocker):
    mocker.patch("core.config.settings.TELEGRAM_CHAT_ID", "12345")
    mocker.patch(
        "core.config.settings.TELEGRAM_BOT_TOKEN",
        "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
    )

    interface = CoraxTelegramInterface(mock_engine)

    # Mock copilot parse_intent
    interface.copilot = AsyncMock()
    interface.copilot.parse_intent.return_value = ("UNKNOWN", None)

    interface.bot = AsyncMock()

    # Mock message from authorized user
    mock_message = AsyncMock()
    mock_message.from_user = MagicMock()
    mock_message.chat = MagicMock()
    mock_message.from_user.id = 12345
    mock_message.chat.id = 12345
    mock_message.text = "Hello"
    mock_message.reply.return_value = MagicMock(message_id=123)

    handlers = interface.dp.message.handlers
    handle_message = handlers[1].callback

    await handle_message(mock_message)

    # Verify reply was called because user is authorized
    mock_message.reply.assert_called_once()


@pytest.mark.asyncio
async def test_telegram_missing_chat_id(mock_engine, mocker):
    mocker.patch("core.config.settings.TELEGRAM_CHAT_ID", None)
    mocker.patch(
        "core.config.settings.TELEGRAM_BOT_TOKEN",
        "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
    )

    interface = CoraxTelegramInterface(mock_engine)

    # Mock message
    mock_message = AsyncMock()
    mock_message.from_user = MagicMock()
    mock_message.chat = MagicMock()
    mock_message.from_user.id = 12345
    mock_message.chat.id = 12345
    mock_message.text = "Hello"

    handlers = interface.dp.message.handlers
    handle_message = handlers[1].callback

    await handle_message(mock_message)

    # Verify reply was not called because TELEGRAM_CHAT_ID is missing
    mock_message.reply.assert_not_called()
