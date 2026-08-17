import pytest
import pytest_asyncio
import asyncio
from core.event_bus import RedisEventBus


@pytest_asyncio.fixture
async def event_bus():
    bus = RedisEventBus()
    yield bus

    # We must explicitly cancel the _listen tasks spawned by asyncio.create_task in the bus
    # We find all tasks and cancel those that match the _listen coroutine
    # The coroutine is an async generator or coroutine object, we can check its __name__
    tasks = []
    for t in asyncio.all_tasks():
        if t is not asyncio.current_task():
            # Get the coroutine object
            coro = t.get_coro()
            if coro and getattr(coro, "__name__", None) == "_listen":
                tasks.append(t)
            elif coro and coro.cr_code.co_name == "_listen":
                tasks.append(t)

    for task in tasks:
        task.cancel()

    if tasks:
        # Await the cancelled tasks to ensure they finish and their exceptions are handled
        await asyncio.gather(*tasks, return_exceptions=True)

    # Ensure any pending tasks get a chance to complete their cancellation
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_subscribe_adds_callback(event_bus):
    async def mock_callback(msg):
        pass

    await event_bus.subscribe("test_channel", mock_callback)

    assert "test_channel" in event_bus.channels
    assert mock_callback in event_bus.channels["test_channel"]


@pytest.mark.asyncio
async def test_subscribe_creates_listen_task_once(event_bus, mocker):
    async def mock_callback(msg):
        pass

    mock_create_task = mocker.patch("asyncio.create_task")

    # When patching create_task, it returns a mock, so no actual task is created
    # However, since the mock returns a mock object, we need to mock it properly
    # to avoid the "never awaited" warning if the mock itself is an async mock, but here it's just a regular mock

    await event_bus.subscribe("test_channel", mock_callback)
    mock_create_task.assert_called_once()

    # We need to manually close the coroutine that was passed to create_task
    # to avoid the "never awaited" warning
    args, kwargs = mock_create_task.call_args
    coro = args[0]
    coro.close()

    await event_bus.subscribe("test_channel", mock_callback)
    mock_create_task.assert_called_once()  # Should not be called again for the same channel


@pytest.mark.asyncio
async def test_publish_and_subscribe(event_bus):
    received_messages = []

    async def mock_callback(msg):
        received_messages.append(msg)

    await event_bus.subscribe("test_channel", mock_callback)
    await event_bus.publish("test_channel", {"type": "test", "data": "hello"})

    # Yield control to the event loop to allow _listen task to process the message
    await asyncio.sleep(0.01)

    assert len(received_messages) == 1
    assert received_messages[0] == {"type": "test", "data": "hello"}


@pytest.mark.asyncio
async def test_multiple_subscribers(event_bus):
    received_messages_1 = []
    received_messages_2 = []

    async def mock_callback_1(msg):
        received_messages_1.append(msg)

    async def mock_callback_2(msg):
        received_messages_2.append(msg)

    await event_bus.subscribe("test_channel", mock_callback_1)
    await event_bus.subscribe("test_channel", mock_callback_2)

    await event_bus.publish("test_channel", {"type": "test", "data": "hello"})

    # Yield control
    await asyncio.sleep(0.01)

    assert len(received_messages_1) == 1
    assert len(received_messages_2) == 1
    assert received_messages_1[0] == {"type": "test", "data": "hello"}
    assert received_messages_2[0] == {"type": "test", "data": "hello"}
