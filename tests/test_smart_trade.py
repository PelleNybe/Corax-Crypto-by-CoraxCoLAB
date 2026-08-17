import pytest
import os

os.environ["EXCHANGE_API_KEY"] = "test"
os.environ["EXCHANGE_API_SECRET"] = "test"
os.environ["LLM_API_KEY"] = "test"
os.environ["CORAX_MODE"] = "testnet"

from core.risk_manager import RiskManager
from core.config import settings


@pytest.mark.asyncio
async def test_trailing_take_profit():
    # Setup
    rm = RiskManager()
    settings.TTP_ACTIVATION_PCT = 0.05  # Activate at 5% profit
    settings.TTP_TRAILING_PCT = 0.015  # 1.5% trailing pullback

    symbol = "ETH/USDT"
    await rm.register_position(symbol, 1000.0, 1.0)

    # 1. Price goes up to 3% profit ($1030). TTP should NOT activate.
    hit = await rm.check_trailing_take_profit(symbol, 1030.0)
    assert not hit
    assert not rm.active_positions[symbol]["ttp_active"]

    # 2. Price hits 5% profit ($1050). TTP ACTIVATES.
    hit = await rm.check_trailing_take_profit(symbol, 1050.0)
    assert not hit  # Doesn't sell, just activates
    assert rm.active_positions[symbol]["ttp_active"]
    assert rm.active_positions[symbol]["ttp_high"] == 1050.0

    # 3. Price goes up to $1100. TTP trails upwards.
    hit = await rm.check_trailing_take_profit(symbol, 1100.0)
    assert not hit
    assert rm.active_positions[symbol]["ttp_high"] == 1100.0

    # 4. Price pulls back to $1090. This is less than 1.5% drop from 1100 (which is 16.5, so 1083.5).
    hit = await rm.check_trailing_take_profit(symbol, 1090.0)
    assert not hit

    # 5. Price pulls back sharply to $1080. This is lower than the trailing floor (1083.5). TTP triggers.
    hit = await rm.check_trailing_take_profit(symbol, 1080.0)
    assert hit
