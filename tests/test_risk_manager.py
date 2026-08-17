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


@pytest.mark.asyncio
async def test_clear_position(mocker):
    rm = RiskManager()
    mock_logger = mocker.patch("core.risk_manager.logger.debug")

    # Setup: Register a position
    await rm.register_position("ETH/USDT", 2000.0, 1.5)
    assert "ETH/USDT" in rm.active_positions
    mock_logger.reset_mock()

    # Action: Clear existing position
    await rm.clear_position("ETH/USDT")

    # Assert: Position is removed
    assert "ETH/USDT" not in rm.active_positions
    mock_logger.assert_called_once_with("Cleared position tracking for ETH/USDT")
    mock_logger.reset_mock()

    # Action/Assert: Clearing a non-existent position should not raise an error
    try:
        await rm.clear_position("BTC/USDT")
        await rm.clear_position("ETH/USDT")  # Try clearing the already cleared one
    except Exception as e:
        pytest.fail(f"clear_position raised an exception unexpectedly: {e}")

    mock_logger.assert_not_called()


@pytest.mark.asyncio
async def test_validate_and_size_hold_action():
    rm = RiskManager()
    rm.peak_balance = 10000.0
    current_balance = 10000.0

    signal = AISignal(
        timestamp=1234567890,
        asset_pair="BTC/USDT",
        action="HOLD",
        confidence_score=0.9,
        reasoning="Test",
    )

    is_valid, size = await rm.validate_and_size(signal, current_balance)
    assert not is_valid
    assert size == 0.0


@pytest.mark.asyncio
async def test_validate_and_size_new_peak_balance_disables_kill_switch(signal):
    rm = RiskManager()
    # Ensure initial sync is done so peak_balance isn't overwritten immediately
    rm.initial_sync_done = True
    rm.peak_balance = 10000.0
    rm.kill_switch_active = True
    current_balance = 11000.0

    is_valid, size = await rm.validate_and_size(signal, current_balance)
    assert is_valid
    assert not rm.kill_switch_active
    assert rm.peak_balance == 11000.0


@pytest.mark.asyncio
async def test_validate_and_size_new_peak_balance_kill_switch_inactive(mocker, signal):
    rm = RiskManager()
    rm.initial_sync_done = True
    rm.peak_balance = 10000.0
    rm.kill_switch_active = False
    current_balance = 11000.0

    mock_logger_info = mocker.patch("core.risk_manager.logger.info")

    is_valid, size = await rm.validate_and_size(signal, current_balance)
    assert is_valid
    assert not rm.kill_switch_active
    assert rm.peak_balance == 11000.0
    mock_logger_info.assert_not_called()


@pytest.mark.asyncio
async def test_check_trailing_stops_symbol_not_found():
    rm = RiskManager()
    result = await rm.check_trailing_stops("NOT_FOUND", 100.0)
    assert not result


@pytest.mark.asyncio
async def test_manual_reset(mocker):
    rm = RiskManager()
    rm.peak_balance = 10000.0
    rm.kill_switch_active = True
    rm.initial_sync_done = False

    mock_logger_success = mocker.patch("core.risk_manager.logger.success")

    await rm.manual_reset(15000.0)

    assert rm.peak_balance == 15000.0
    assert not rm.kill_switch_active
    assert rm.initial_sync_done

    mock_logger_success.assert_called_once_with(
        "🛡️ RiskManager manually reset. New baseline: $15000.00 USDC"
    )


@pytest.mark.asyncio
async def test_check_trailing_take_profit():
    from core.config import settings

    # Store old settings
    old_ttp_activation_pct = settings.TTP_ACTIVATION_PCT
    old_ttp_trailing_pct = settings.TTP_TRAILING_PCT

    # Set known test settings
    settings.TTP_ACTIVATION_PCT = 0.02  # 2%
    settings.TTP_TRAILING_PCT = 0.01  # 1%

    rm = RiskManager()
    symbol = "ETH/USDT"
    entry_price = 2000.0

    # Position not registered
    assert not await rm.check_trailing_take_profit(symbol, 2050.0)

    # Register position
    await rm.register_position(symbol, entry_price, 1.0)

    # 1. Price increases but not enough to trigger TTP activation (1%)
    assert not await rm.check_trailing_take_profit(symbol, 2020.0)
    assert not rm.active_positions[symbol].get("ttp_active", False)

    # 2. Price increases enough to trigger TTP activation (3%)
    assert not await rm.check_trailing_take_profit(symbol, 2060.0)
    assert rm.active_positions[symbol]["ttp_active"]
    assert rm.active_positions[symbol]["ttp_high"] == 2060.0

    # 3. Price goes even higher, updating TTP high watermark
    assert not await rm.check_trailing_take_profit(symbol, 2100.0)
    assert rm.active_positions[symbol]["ttp_high"] == 2100.0

    # 4. Price drops slightly, but doesn't hit trailing floor (2100 * 0.99 = 2079)
    assert not await rm.check_trailing_take_profit(symbol, 2080.0)

    # 5. Price drops below trailing floor, triggers smart trade
    assert await rm.check_trailing_take_profit(symbol, 2075.0)

    # Restore old settings
    settings.TTP_ACTIVATION_PCT = old_ttp_activation_pct
    settings.TTP_TRAILING_PCT = old_ttp_trailing_pct


@pytest.mark.asyncio
async def test_check_trailing_stops_exact_price():
    rm = RiskManager()
    rm.trailing_stop_pct = 0.10  # 10%

    await rm.register_position("BTC/USDT", 10000.0, 1.0)
    assert rm.active_positions["BTC/USDT"]["trailing_stop_price"] == 9000.0

    # Exactly at stop price should trigger
    assert await rm.check_trailing_stops("BTC/USDT", 9000.0)


@pytest.mark.asyncio
async def test_check_trailing_stops_only_trail_upwards(mocker):
    rm = RiskManager()
    rm.trailing_stop_pct = 0.10

    await rm.register_position("BTC/USDT", 10000.0, 1.0)

    # Artificially set a high trailing stop price to test the "only trail upwards" branch
    rm.active_positions["BTC/USDT"]["trailing_stop_price"] = 9500.0

    mock_logger = mocker.patch("core.risk_manager.logger.debug")

    # Price goes up to 10100, high_watermark updates to 10100.
    # new_tsl = 10100 * 0.9 = 9090.
    # 9090 is NOT > 9500, so trailing_stop_price should not update.
    assert not await rm.check_trailing_stops("BTC/USDT", 10100.0)

    assert rm.active_positions["BTC/USDT"]["high_watermark"] == 10100.0
    assert rm.active_positions["BTC/USDT"]["trailing_stop_price"] == 9500.0

    # Verify logger.debug for trailing stop updated was NOT called
    mock_logger.assert_not_called()


@pytest.mark.asyncio
async def test_check_trailing_stops_logging(mocker):
    rm = RiskManager()
    rm.trailing_stop_pct = 0.10

    mock_logger_debug = mocker.patch("core.risk_manager.logger.debug")
    mock_logger_warning = mocker.patch("core.risk_manager.logger.warning")

    await rm.register_position("BTC/USDT", 10000.0, 1.0)
    assert rm.active_positions["BTC/USDT"]["trailing_stop_price"] == 9000.0
    mock_logger_debug.reset_mock()
    mock_logger_warning.reset_mock()

    # Price goes up, high watermark and TSL updated.
    # TSL = 11000 * 0.9 = 9900
    assert not await rm.check_trailing_stops("BTC/USDT", 11000.0)
    mock_logger_debug.assert_called_once_with(
        "[BTC/USDT] Trailing stop updated to 9900.00"
    )
    mock_logger_warning.assert_not_called()

    mock_logger_debug.reset_mock()

    # Price falls below TSL (9900), triggering it.
    assert await rm.check_trailing_stops("BTC/USDT", 9800.0)
    mock_logger_warning.assert_called_once_with(
        "🚨 TSL TRIGGERED for BTC/USDT: Price 9800.00 fell below stop 9900.00"
    )
    mock_logger_debug.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "current_price, expected_trigger, expected_hwm, expected_tsl",
    [
        # Initial: entry=10000, TSL=9000, HWM=10000
        (10500.0, False, 10500.0, 9450.0),  # Price increases: updates HWM and TSL
        (10000.0, False, 10000.0, 9000.0),  # Price equals HWM: no updates
        (9500.0, False, 10000.0, 9000.0),  # Price decreases but above TSL: no updates
        (9000.0, True, 10000.0, 9000.0),  # Price equals TSL: triggers
        (8500.0, True, 10000.0, 9000.0),  # Price below TSL: triggers
    ],
)
async def test_check_trailing_stops_scenarios(
    current_price, expected_trigger, expected_hwm, expected_tsl
):
    rm = RiskManager()
    rm.trailing_stop_pct = 0.10  # 10%

    await rm.register_position("BTC/USDT", 10000.0, 1.0)

    triggered = await rm.check_trailing_stops("BTC/USDT", current_price)

    assert triggered == expected_trigger
    assert rm.active_positions["BTC/USDT"]["high_watermark"] == expected_hwm
    assert rm.active_positions["BTC/USDT"]["trailing_stop_price"] == expected_tsl


@pytest.mark.asyncio
async def test_check_trailing_stops_sequence():
    rm = RiskManager()
    rm.trailing_stop_pct = 0.10

    await rm.register_position("BTC/USDT", 10000.0, 1.0)

    # 1. Price increases
    assert not await rm.check_trailing_stops("BTC/USDT", 11000.0)
    assert rm.active_positions["BTC/USDT"]["high_watermark"] == 11000.0
    assert rm.active_positions["BTC/USDT"]["trailing_stop_price"] == 9900.0

    # 2. Price decreases slightly (above TSL)
    assert not await rm.check_trailing_stops("BTC/USDT", 10500.0)
    assert rm.active_positions["BTC/USDT"]["high_watermark"] == 11000.0
    assert rm.active_positions["BTC/USDT"]["trailing_stop_price"] == 9900.0

    # 3. Price increases more
    assert not await rm.check_trailing_stops("BTC/USDT", 12000.0)
    assert rm.active_positions["BTC/USDT"]["high_watermark"] == 12000.0
    assert rm.active_positions["BTC/USDT"]["trailing_stop_price"] == 10800.0

    # 4. Price drops below TSL
    assert await rm.check_trailing_stops("BTC/USDT", 10700.0)


@pytest.mark.asyncio
async def test_validate_and_size_initial_sync(signal):
    rm = RiskManager()
    assert not rm.initial_sync_done
    assert rm.peak_balance == 0.0

    current_balance = 10000.0
    is_valid, size = await rm.validate_and_size(signal, current_balance)

    assert rm.initial_sync_done
    assert rm.peak_balance == 10000.0
    assert is_valid


@pytest.mark.asyncio
async def test_validate_and_size_zero_balance(signal):
    rm = RiskManager()
    current_balance = 0.0
    is_valid, size = await rm.validate_and_size(signal, current_balance)

    assert not rm.initial_sync_done
    assert rm.peak_balance == 0.0
    assert size == 0.0


@pytest.mark.asyncio
async def test_validate_and_size_kill_switch_allows_sell():
    rm = RiskManager()
    rm.initial_sync_done = True
    rm.peak_balance = 10000.0
    rm.kill_switch_active = True
    current_balance = 9000.0

    signal = AISignal(
        timestamp=1234567890,
        asset_pair="BTC/USDT",
        action="SELL",
        confidence_score=0.9,
        reasoning="Test",
    )

    is_valid, size = await rm.validate_and_size(signal, current_balance)
    assert is_valid
    assert size > 0.0


@pytest.mark.asyncio
async def test_validate_and_size_kill_switch_already_active_suppresses_log(
    mocker, signal
):
    rm = RiskManager()
    rm.initial_sync_done = True
    rm.peak_balance = 10000.0
    rm.max_daily_drawdown = 0.05
    rm.kill_switch_active = True  # Already active

    mock_logger_warning = mocker.patch("core.risk_manager.logger.warning")

    current_balance = 9000.0  # 10% drawdown
    is_valid, size = await rm.validate_and_size(signal, current_balance)

    assert not is_valid
    assert rm.kill_switch_active
    mock_logger_warning.assert_not_called()
