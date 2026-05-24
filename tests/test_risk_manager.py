import pytest
import datetime
from core.risk_manager import RiskManager
from schemas.signals import AISignal


@pytest.fixture
def signal():
    return AISignal(
        timestamp=1234567890,
        asset_pair="BTC/USDT",
        action="BUY",
        confidence_score=0.9,
        reasoning="Test",
    )


@pytest.mark.asyncio
async def test_daily_drawdown_kill_switch(signal):
    rm = RiskManager()
    rm.max_daily_drawdown = 0.05
    rm.max_risk_per_trade = 0.01

    rm.peak_balance = 10000.0
    current_balance = 10000.0

    # Normal execution
    is_valid, size = await rm.validate_and_size(signal, current_balance)
    assert is_valid
    assert size == 100.0
    assert not rm.kill_switch_active

    # 6% drawdown activates Kill Switch
    current_balance = 9400.0
    is_valid, size = await rm.validate_and_size(signal, current_balance)
    assert not is_valid
    assert size == 0.0
    assert rm.kill_switch_active


@pytest.mark.asyncio
async def test_utc_midnight_reset(signal):
    rm = RiskManager()
    rm.peak_balance = 10000.0
    rm.kill_switch_active = True

    # Mock date to be in the past
    past_date = datetime.datetime.now(
        datetime.timezone.utc
    ).date() - datetime.timedelta(days=1)
    rm.last_reset_date = past_date

    # Run validate with current balance lower than peak (e.g. 9400.0)
    # The midnight reset should set the peak balance to 9400.0 and disable the kill switch.
    current_balance = 9400.0
    is_valid, size = await rm.validate_and_size(signal, current_balance)

    assert rm.peak_balance == 9400.0
    assert not rm.kill_switch_active
    assert is_valid
    assert size > 0.0


@pytest.mark.asyncio
async def test_trailing_stop_loss():
    rm = RiskManager()
    rm.trailing_stop_pct = 0.05  # 5% trailing stop

    # Register a new position
    await rm.register_position("BTC/USDT", 50000.0, 1.0)

    # Initial state
    assert rm.active_positions["BTC/USDT"]["trailing_stop_price"] == 47500.0

    # Price drops slightly, but doesn't trigger TSL
    assert not await rm.check_trailing_stops("BTC/USDT", 48000.0)

    # Price goes up, updating high watermark and TSL
    assert not await rm.check_trailing_stops("BTC/USDT", 60000.0)
    assert rm.active_positions["BTC/USDT"]["high_watermark"] == 60000.0
    assert rm.active_positions["BTC/USDT"]["trailing_stop_price"] == 57000.0

    # Price drops significantly, triggering TSL
    assert await rm.check_trailing_stops("BTC/USDT", 56000.0)

    # Clear position
    await rm.clear_position("BTC/USDT")
    assert "BTC/USDT" not in rm.active_positions
