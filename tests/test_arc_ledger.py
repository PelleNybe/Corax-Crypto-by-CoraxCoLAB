import pytest
import time
from unittest.mock import AsyncMock, patch

from core.arc_ledger import ArcLedger
from schemas.orders import OrderContext
from core.state import global_state


@pytest.fixture
def ledger():
    with (
        patch("core.arc_ledger.settings.CIRCLE_API_KEY", "test_key"),
        patch("core.arc_ledger.settings.CIRCLE_WALLET_ID", "test_wallet"),
        patch("core.arc_ledger.settings.CIRCLE_ENTITY_SECRET", "test_secret"),
    ):
        ledger = ArcLedger(initial_capital=10000.0)
        # reset sync time to allow immediate sync
        ledger._last_sync_time = 0.0
        return ledger


@pytest.fixture
def empty_ledger():
    with (
        patch("core.arc_ledger.settings.CIRCLE_API_KEY", ""),
        patch("core.arc_ledger.settings.CIRCLE_WALLET_ID", ""),
    ):
        ledger = ArcLedger(initial_capital=10000.0)
        ledger._last_sync_time = 0.0
        return ledger


def test_process_balance_response(ledger):
    # Test with USDC
    data = {
        "tokenBalances": [
            {"token": {"symbol": "BTC"}, "amount": "1.0"},
            {"token": {"symbol": "USDC"}, "amount": "1234.56"},
        ]
    }
    ledger._process_balance_response(data)
    assert ledger.balance == 1234.56

    # Test with USD
    data = {"tokenBalances": [{"token": {"symbol": "USD"}, "amount": "999.99"}]}
    ledger._process_balance_response(data)
    assert ledger.balance == 999.99

    # Test no USDC/USD
    data = {"tokenBalances": [{"token": {"symbol": "ETH"}, "amount": "10.0"}]}
    ledger._process_balance_response(data)
    assert ledger.balance == 0.0

    # Test invalid data format (missing keys)
    data = {"tokenBalances": [{"invalid": "format"}]}
    ledger.balance = 50.0  # Should be reset to 0
    ledger._process_balance_response(data)
    assert ledger.balance == 0.0


def test_sync_balance_sync_success(ledger):
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json.return_value = {
            "data": {
                "tokenBalances": [{"token": {"symbol": "USDC"}, "amount": "100.0"}]
            }
        }
        mock_resp.__aenter__.return_value = mock_resp
        mock_get.return_value = mock_resp

        ledger._sync_balance_sync(force=True)
        assert ledger.balance == 100.0
        mock_get.assert_called_once()


def test_sync_balance_sync_missing_creds(empty_ledger):
    with patch("aiohttp.ClientSession.get") as mock_get:
        empty_ledger._sync_balance_sync(force=True)
        mock_get.assert_not_called()


def test_sync_balance_sync_cooldown(ledger):
    ledger._last_sync_time = time.monotonic()
    with patch("aiohttp.ClientSession.get") as mock_get:
        ledger._sync_balance_sync(force=False)
        mock_get.assert_not_called()


def test_sync_balance_sync_error(ledger):
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 400
        mock_resp.text.return_value = "Bad Request"
        mock_resp.__aenter__.return_value = mock_resp
        mock_get.return_value = mock_resp

        ledger.balance = 50.0
        ledger._sync_balance_sync(force=True)
        assert ledger.balance == 50.0  # Balance unchanged

    with patch(
        "requests.get",
        side_effect=Exception("Network Error"),
    ):
        ledger._sync_balance_sync(force=True)
        assert ledger.balance == 50.0

    with patch("requests.get", side_effect=Exception("Generic Error")):
        ledger._sync_balance_sync(force=True)
        assert ledger.balance == 50.0


@pytest.mark.asyncio
async def test_sync_balance_async_success(ledger):
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json.return_value = {
            "data": {
                "tokenBalances": [{"token": {"symbol": "USDC"}, "amount": "200.0"}]
            }
        }
        mock_resp.__aenter__.return_value = mock_resp
        mock_get.return_value = mock_resp

        await ledger._sync_balance(force=True)
        assert ledger.balance == 200.0


@pytest.mark.asyncio
async def test_sync_balance_async_missing_creds(empty_ledger):
    with patch("aiohttp.ClientSession.get") as mock_get:
        await empty_ledger._sync_balance(force=True)
        mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_sync_balance_async_cooldown(ledger):
    ledger._last_sync_time = time.monotonic()
    with patch("aiohttp.ClientSession.get") as mock_get:
        await ledger._sync_balance(force=False)
        mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_sync_balance_async_error(ledger):
    ledger.balance = 50.0
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 400
        mock_resp.text.return_value = "Bad Request"
        mock_resp.__aenter__.return_value = mock_resp
        mock_get.return_value = mock_resp

        await ledger._sync_balance(force=True)
        assert ledger.balance == 50.0  # Unchanged

    with patch(
        "aiohttp.ClientSession.get", side_effect=Exception("Generic Async Error")
    ):
        await ledger._sync_balance(force=True)
        assert ledger.balance == 50.0


@pytest.mark.asyncio
async def test_refresh_balance(ledger):
    with patch.object(ledger, "_sync_balance", new_callable=AsyncMock) as mock_sync:
        ledger.balance = 300.0
        bal = await ledger.refresh_balance()
        assert bal == 300.0
        mock_sync.assert_called_once_with(force=True)


@pytest.mark.asyncio
async def test_arc_ledger_execution(ledger):
    async def mock_sync():
        ledger.balance = 10000.0

    ledger._sync_balance = mock_sync

    context = OrderContext(
        symbol="BTC/USDC",
        side="buy",
        order_type="market",
        amount=0.1,
        current_price=50000.0,
    )

    # Test tracking behavior
    success = await ledger.execute_virtual_order(context)
    assert success is True

    # Amount * price * (1+slip) = 0.1 * 50000 * 1.001 = 5005
    assert ledger.balance == 10000.0 - 5005.0
    assert ledger.positions["BTC/USDC"] == 0.1


@pytest.mark.asyncio
async def test_arc_ledger_execution_edge_cases(ledger):
    async def mock_sync():
        pass

    ledger._sync_balance = mock_sync
    ledger.balance = 100.0
    ledger.positions = {"ETH/USDC": 1.0}

    # 1. Buy with insufficient balance
    context_buy = OrderContext(
        symbol="BTC/USDC",
        side="buy",
        order_type="market",
        amount=0.1,
        current_price=50000.0,
    )
    success = await ledger.execute_virtual_order(context_buy)
    assert success is False
    assert ledger.balance == 100.0
    assert "BTC/USDC" not in ledger.positions

    # 2. Sell with insufficient asset
    context_sell_insufficient = OrderContext(
        symbol="ETH/USDC",
        side="sell",
        order_type="market",
        amount=2.0,
        current_price=3000.0,
    )
    success = await ledger.execute_virtual_order(context_sell_insufficient)
    assert success is False
    assert ledger.balance == 100.0
    assert ledger.positions["ETH/USDC"] == 1.0

    # 3. Sell happy path
    context_sell = OrderContext(
        symbol="ETH/USDC",
        side="sell",
        order_type="market",
        amount=0.5,
        current_price=3000.0,
    )
    success = await ledger.execute_virtual_order(context_sell)
    assert success is True
    # Gain = 0.5 * 3000 * (1 - 0.001) = 1500 * 0.999 = 1498.5
    assert ledger.balance == 100.0 + 1498.5
    assert ledger.positions["ETH/USDC"] == 0.5

    # 4. Fallback to global_state for current_price
    global_state.latest_prices["DOGE/USDC"] = 0.1
    context_missing_price = OrderContext(
        symbol="DOGE/USDC",
        side="buy",
        order_type="market",
        amount=100.0,
        current_price=0.0,
    )
    ledger.balance = 1000.0
    success = await ledger.execute_virtual_order(context_missing_price)
    assert success is True
    # trade_cost = 100 * 0.1 * 1.001 = 10.01
    assert ledger.balance == pytest.approx(1000.0 - 10.01, rel=1e-5)
    assert ledger.positions["DOGE/USDC"] == 100.0


def test_arc_ledger_reset_ledger():
    ledger = ArcLedger(initial_capital=10000.0)
    with pytest.raises(
        NotImplementedError, match="reset_ledger is not supported for live ArcLedger."
    ):
        ledger.reset_ledger()


@pytest.mark.asyncio
async def test_arc_ledger_init_async():
    # To hit line 61, we need to initialize ArcLedger inside a running async loop
    with (
        patch("core.arc_ledger.settings.CIRCLE_API_KEY", "test_key"),
        patch("core.arc_ledger.settings.CIRCLE_WALLET_ID", "test_wallet"),
        patch("core.arc_ledger.settings.CIRCLE_ENTITY_SECRET", "test_secret"),
    ):
        # this is in an async test so get_running_loop() should succeed
        with patch.object(ArcLedger, "_sync_balance") as mock_sync:
            _ = ArcLedger(initial_capital=1000.0)
            mock_sync.assert_called_once_with(force=True)


@pytest.mark.asyncio
async def test_arc_ledger_execution_zero_price(ledger):
    async def mock_sync():
        pass

    ledger._sync_balance = mock_sync
    ledger.balance = 1000.0

    # 5. Missing price and not in global_state -> zero price error
    # Clear out global state to ensure it defaults to 0.0
    from core.state import global_state

    if "ZERO_PRICE/USDC" in global_state.latest_prices:
        del global_state.latest_prices["ZERO_PRICE/USDC"]

    context_zero_price = OrderContext(
        symbol="ZERO_PRICE/USDC",
        side="buy",
        order_type="market",
        amount=10.0,
        current_price=0.0,
    )
    success = await ledger.execute_virtual_order(context_zero_price)
    assert success is False
    assert ledger.balance == 1000.0
    assert "ZERO_PRICE/USDC" not in ledger.positions
    assert len(ledger.trade_history) == 0


@pytest.mark.asyncio
async def test_arc_ledger_execution_invalid_side(ledger):
    async def mock_sync():
        pass

    ledger._sync_balance = mock_sync
    ledger.balance = 1000.0

    context_invalid_side = OrderContext(
        symbol="BTC/USDC",
        side="unknown_side",
        order_type="market",
        amount=0.1,
        current_price=50000.0,
    )
    success = await ledger.execute_virtual_order(context_invalid_side)
    assert success is False
    assert ledger.balance == 1000.0
    assert "BTC/USDC" not in ledger.positions
    assert len(ledger.trade_history) == 0


@pytest.mark.asyncio
async def test_arc_ledger_trade_history_population(ledger):
    async def mock_sync():
        pass

    ledger._sync_balance = mock_sync
    ledger.balance = 10000.0
    ledger.positions = {"ETH/USDC": 1.0}

    # Do a successful buy
    context_buy = OrderContext(
        symbol="BTC/USDC",
        side="buy",
        order_type="market",
        amount=0.1,
        current_price=50000.0,
    )
    success1 = await ledger.execute_virtual_order(context_buy)
    assert success1 is True
    assert len(ledger.trade_history) == 1

    trade1 = ledger.trade_history[0]
    assert trade1["symbol"] == "BTC/USDC"
    assert trade1["side"] == "buy"
    assert trade1["amount"] == 0.1
    # Check slippage was applied correctly (50000 * 1.001)
    assert trade1["price"] == pytest.approx(50050.0, rel=1e-5)
    # Expected balance: 10000.0 - 5005.0 = 4995.0
    assert trade1["balance_after"] == pytest.approx(4995.0, rel=1e-5)

    # Do a successful sell
    context_sell = OrderContext(
        symbol="ETH/USDC",
        side="sell",
        order_type="market",
        amount=0.5,
        current_price=3000.0,
    )
    success2 = await ledger.execute_virtual_order(context_sell)
    assert success2 is True
    assert len(ledger.trade_history) == 2

    trade2 = ledger.trade_history[1]
    assert trade2["symbol"] == "ETH/USDC"
    assert trade2["side"] == "sell"
    assert trade2["amount"] == 0.5
    # Check slippage was applied correctly (3000 * (1 - 0.001))
    assert trade2["price"] == 2997.0
    # Gain: 0.5 * 2997.0 = 1498.5. Expected balance: 4995.0 + 1498.5 = 6493.5
    assert trade2["balance_after"] == pytest.approx(6493.5, rel=1e-5)
