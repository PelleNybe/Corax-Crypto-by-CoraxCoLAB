import pytest
from core.state import GlobalState


@pytest.mark.asyncio
async def test_global_state_initialization():
    state = GlobalState()
    assert len(state.recent_ticks) == 0
    assert state.latest_signal is None
    assert state.current_balance == 10000.0
    assert len(state.active_connections) == 0


@pytest.mark.asyncio
async def test_global_state_updates():
    state = GlobalState()

    # Test balance update
    await state.update_balance(1000.0)
    assert state.current_balance == 1000.0

    # Test tick update
    mock_tick = {"price": 50000.0, "symbol": "BTC/USDT", "timestamp": 1234567890}
    await state.update_tick(mock_tick)
    assert len(state.recent_ticks) == 1
    assert state.recent_ticks[0] == mock_tick

    # Test update metric
    await state.update_metric("test_metric", 5.0)
    assert state.metrics["test_metric"] == 5.0


@pytest.mark.asyncio
async def test_global_state_broadcasting():
    state = GlobalState()
    queue = await state.add_connection()
    assert len(state.active_connections) == 1

    # Broadcast an event
    await state._broadcast({"type": "test", "data": "hello"})

    # Check queue receives it
    msg = await queue.get()
    assert msg["type"] == "test"
    assert msg["data"] == "hello"

    # Remove connection
    await state.remove_connection(queue)
    assert len(state.active_connections) == 0
