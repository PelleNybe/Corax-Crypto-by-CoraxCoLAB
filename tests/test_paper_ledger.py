import pytest
from core.paper_ledger import PaperLedger
from schemas.orders import OrderContext


def test_paper_ledger_initialization():
    ledger = PaperLedger(initial_capital=5000.0)
    assert ledger.initial_capital == 5000.0
    assert ledger.balance == 5000.0
    assert len(ledger.positions) == 0


def test_paper_ledger_reset():
    ledger = PaperLedger(initial_capital=1000.0)
    ledger.balance = 500.0
    ledger.positions["BTC"] = 1.0

    ledger.reset_ledger()
    assert ledger.balance == 1000.0
    assert len(ledger.positions) == 0


@pytest.mark.asyncio
async def test_paper_ledger_execute_buy():
    ledger = PaperLedger(initial_capital=10000.0, maker_fee=0.001)

    context = OrderContext(
        symbol="BTC/USDT",
        side="buy",
        order_type="limit",
        amount=0.1,
        current_price=50000.0,
    )

    success = await ledger.execute_virtual_order(context)
    assert success is True

    # Cost = 5000 + 0.001 * 5000 = 5005
    assert ledger.balance == 10000.0 - 5005.0
    assert ledger.positions["BTC/USDT"] == 0.1

    assert len(ledger.trade_history) == 1
    assert ledger.trade_history[0]["amount"] == 0.1


@pytest.mark.asyncio
async def test_paper_ledger_execute_sell():
    ledger = PaperLedger(initial_capital=10000.0, maker_fee=0.001)
    ledger.positions["BTC/USDT"] = 0.5

    context = OrderContext(
        symbol="BTC/USDT",
        side="sell",
        order_type="limit",
        amount=0.1,
        current_price=60000.0,
    )

    success = await ledger.execute_virtual_order(context)
    assert success is True

    # Proceeds = 6000. Fee = 6. Net = 5994.
    assert ledger.balance == 15994.0
    assert ledger.positions["BTC/USDT"] == 0.4


@pytest.mark.asyncio
async def test_paper_ledger_insufficient_funds():
    ledger = PaperLedger(initial_capital=1000.0)
    context = OrderContext(
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        amount=1.0,
        current_price=50000.0,
    )

    success = await ledger.execute_virtual_order(context)
    assert success is False
    assert ledger.balance == 1000.0


def test_paper_ledger_init_default_capital():
    from core.config import settings

    ledger = PaperLedger()
    assert ledger.initial_capital == settings.PAPER_BALANCE_USDT
    assert ledger.balance == settings.PAPER_BALANCE_USDT


def test_paper_ledger_slippage_simulation():
    ledger = PaperLedger()

    # Limit order slippage should be 0.0
    limit_slip = ledger._simulate_slippage("limit", 10.0)
    assert limit_slip == 0.0

    # Market order small volume slippage
    market_slip = ledger._simulate_slippage("market", 1000.0)
    assert market_slip == 0.0005 + (1000.0 / 100000.0) * 0.001

    # Market order large volume slippage capped at 0.02
    market_slip_capped = ledger._simulate_slippage("market", 5000000.0)
    assert market_slip_capped == 0.02


@pytest.mark.asyncio
async def test_paper_ledger_execute_no_price():
    from core.state import global_state

    # Mock get_summary since we can't easily set last_price via update_tick for a fake symbol without setting up tick models
    original_get_summary = global_state.get_summary
    global_state.get_summary = lambda: {"price_BTC/USDT": 55000.0}

    ledger = PaperLedger(initial_capital=100000.0, maker_fee=0.0)

    context = OrderContext(
        symbol="BTC/USDT",
        side="buy",
        order_type="limit",
        amount=1.0,
        current_price=0.0,  # no price
    )

    success = await ledger.execute_virtual_order(context)
    assert success is True
    assert ledger.balance == 100000.0 - 55000.0
    assert ledger.positions["BTC/USDT"] == 1.0

    # Restore mock
    global_state.get_summary = original_get_summary


@pytest.mark.asyncio
async def test_paper_ledger_sell_insufficient_asset():
    ledger = PaperLedger(initial_capital=10000.0)
    ledger.positions["BTC/USDT"] = 0.5

    context = OrderContext(
        symbol="BTC/USDT",
        side="sell",
        order_type="limit",
        amount=1.0,  # more than we have
        current_price=60000.0,
    )

    success = await ledger.execute_virtual_order(context)
    assert success is False
    assert ledger.positions["BTC/USDT"] == 0.5  # unchanged
    assert ledger.balance == 10000.0  # unchanged


@pytest.mark.asyncio
async def test_paper_ledger_buy_market_with_slippage():
    ledger = PaperLedger(initial_capital=100000.0, taker_fee=0.001)

    context = OrderContext(
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        amount=1.0,
        current_price=50000.0,
    )

    # Calculate expected slip manually
    expected_slip = 0.0005 + (1.0 / 100000.0) * 0.001
    exec_price = 50000.0 * (1 + expected_slip)
    gross = exec_price * 1.0
    fee = gross * 0.001

    success = await ledger.execute_virtual_order(context)
    assert success is True

    assert ledger.balance == pytest.approx(100000.0 - (gross + fee), rel=1e-5)
    assert ledger.positions["BTC/USDT"] == 1.0


@pytest.mark.asyncio
async def test_paper_ledger_sell_market_with_slippage():
    ledger = PaperLedger(initial_capital=10000.0, taker_fee=0.001)
    ledger.positions["BTC/USDT"] = 1.0

    context = OrderContext(
        symbol="BTC/USDT",
        side="sell",
        order_type="market",
        amount=1.0,
        current_price=50000.0,
    )

    expected_slip = 0.0005 + (1.0 / 100000.0) * 0.001
    exec_price = 50000.0 * (1 - expected_slip)
    gross = exec_price * 1.0
    fee = gross * 0.001

    success = await ledger.execute_virtual_order(context)
    assert success is True

    assert ledger.balance == pytest.approx(10000.0 + (gross - fee), rel=1e-5)
    assert ledger.positions["BTC/USDT"] == 0.0
