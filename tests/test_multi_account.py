import pytest
import os
import json
from unittest.mock import patch, MagicMock, AsyncMock

os.environ["EXCHANGE_API_KEY"] = "test"
os.environ["EXCHANGE_API_SECRET"] = "test"
os.environ["LLM_API_KEY"] = "test"
os.environ["CORAX_MODE"] = "testnet"

from core.config import settings
from execution.exchange_manager import exchange_manager
from execution.order_manager import OrderManager
from core.risk_manager import RiskManager
from schemas.signals import AISignal
from core.state import global_state


@pytest.mark.asyncio
async def test_multi_account_init():
    settings.COPY_TRADE_ENABLED = True
    settings.CORAX_MODE = (
        "mainnet"  # ensure we are not strictly micro-sizing things to dust threshold
    )
    settings.DRY_RUN_MODE = False  # to be able to hit standard code paths
    settings.EXCHANGE_ID = "binance"
    multi_config = {
        "sub1": {"exchange": "kraken", "apiKey": "x", "secret": "y"},
        "sub2": {"exchange": "binance", "apiKey": "a", "secret": "b"},
    }
    settings.MULTI_ACCOUNT_CONFIG = json.dumps(multi_config)

    mock_binance = MagicMock()
    mock_kraken = MagicMock()

    with patch("execution.exchange_manager.ccxtpro.binance", return_value=mock_binance):
        with patch(
            "execution.exchange_manager.ccxtpro.kraken", return_value=mock_kraken
        ):
            await exchange_manager.initialize()

            assert "binance" in exchange_manager.exchanges
            assert "kraken_sub1" in exchange_manager.exchanges
            assert "binance_sub2" in exchange_manager.exchanges


@pytest.mark.asyncio
async def test_multi_account_routing():
    settings.COPY_TRADE_ENABLED = True
    settings.CORAX_MODE = (
        "mainnet"  # ensure we are not strictly micro-sizing things to dust threshold
    )
    settings.DRY_RUN_MODE = False  # to be able to hit standard code paths
    multi_config = {
        "sub1": {"exchange": "kraken", "apiKey": "x", "secret": "y"},
        "sub2": {"exchange": "binance", "apiKey": "a", "secret": "b"},
    }
    settings.MULTI_ACCOUNT_CONFIG = json.dumps(multi_config)

    exchange_manager.exchanges = {
        "binance": MagicMock(),
        "kraken_sub1": MagicMock(),
        "binance_sub2": MagicMock(),
    }

    rm = RiskManager()
    om = OrderManager(rm)

    om._running = False  # Stop background worker

    # We don't want the worker to consume tasks immediately so we can inspect the queue size
    queued_items = []

    async def mock_put(item):
        queued_items.append(item)

    om.order_queue.put = mock_put

    signal = AISignal(
        timestamp=123,
        asset_pair="BTC/USDT",
        action="BUY",
        confidence_score=1.0,
        reasoning="Test Multi",
    )

    om.is_dry_run = True  # force dry run mode to bypass fetch_balance exceptions
    global_state.price_BTCUSDT = 50000.0  # set a price so risk sizing doesn't fail

    om.available_balance = 1000.0

    # Risk manager size depends on validate_and_size which depends on position checks. Mock it.
    rm.validate_and_size = AsyncMock(return_value=(True, 0.5))

    await om.execute_signal(signal)

    assert len(queued_items) == 3

    task1 = queued_items[0]
    task2 = queued_items[1]
    task3 = queued_items[2]

    exchanges_queued = [
        task1[1]["exchange_id"],
        task2[1]["exchange_id"],
        task3[1]["exchange_id"],
    ]
    assert "binance" in exchanges_queued
    assert "kraken_sub1" in exchanges_queued
    assert "binance_sub2" in exchanges_queued
