import pytest
import os

os.environ["EXCHANGE_API_KEY"] = "test"
os.environ["EXCHANGE_API_SECRET"] = "test"
os.environ["LLM_API_KEY"] = "test"
os.environ["CORAX_MODE"] = "testnet"

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from core.config import settings
from execution.exchange_manager import exchange_manager


@pytest.mark.asyncio
async def test_futures_config_init():
    settings.MARKET_TYPE = "future"
    settings.LEVERAGE = 10
    settings.ARBITRAGE_EXCHANGES = ["binance"]
    settings.EXCHANGE_ID = "binance"

    mock_ex = MagicMock()
    mock_ex.load_markets = AsyncMock()
    mock_ex.set_leverage = AsyncMock()
    mock_ex.markets = {"BTC/USDT:USDT": True}

    with patch("execution.exchange_manager.ccxtpro.binance", return_value=mock_ex):
        await exchange_manager.initialize()

        # We need to wait a tick for the background task `set_leverage` to finish
        await asyncio.sleep(0.1)

        # Check leverage was set
        assert mock_ex.set_leverage.call_count >= 1

    settings.MARKET_TYPE = "spot"
    settings.LEVERAGE = 1
