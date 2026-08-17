import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from execution.order_manager import OrderManager
from core.risk_manager import RiskManager
from schemas.signals import AISignal


@pytest.fixture
def risk_manager():
    rm = RiskManager()
    rm.max_risk_per_trade = 0.01
    return rm


@pytest.fixture
def buy_signal():
    return AISignal(
        timestamp=1234567890,
        asset_pair="BTC/USDT",
        action="BUY",
        confidence_score=0.9,
        reasoning="Test",
    )


@pytest.mark.asyncio
async def test_dry_run_routes_to_paper_ledger(risk_manager, buy_signal, mocker):
    mocker.patch("core.config.settings.DRY_RUN_MODE", True)

    with patch("core.config.settings.DRY_RUN_MODE", True):
        # In the context of aiohttp, mock the specific method used or rely on existing mocks.
        # Since arc_ledger now uses aiohttp, we mock ClientSession.get
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "data": {"balances": [{"currency": "USD", "amount": "10000.0"}]}
            }
        )

        mocker.patch("aiohttp.ClientSession.get", return_value=mock_response)
        mock_post_response = AsyncMock()
        mock_post_response.status = 200
        mock_post_response.json = AsyncMock(return_value={})
        mocker.patch("aiohttp.ClientSession.post", return_value=mock_post_response)

        # Reset risk manager balance peak since mock might have run
        risk_manager.daily_peak_balance = 10000.0
        risk_manager.kill_switch_active = False

        order_manager = OrderManager(risk_manager=risk_manager)

        # Patch paper ledger
        order_manager.paper_ledger.execute_virtual_order = AsyncMock()

        # Patch exchange manager (just in case)
        mocker.patch(
            "execution.order_manager.exchange_manager.execute_order",
            new_callable=AsyncMock,
        )

        # Execute signal
        await order_manager.execute_signal(buy_signal)

        # Wait for queue worker to process
        await asyncio.sleep(0.1)

        # The mock exchange should NOT be called
        from execution.order_manager import exchange_manager

        exchange_manager.execute_order.assert_not_called()

        # Paper ledger SHOULD be called
        assert order_manager.paper_ledger.execute_virtual_order.call_count > 0

        # Shutdown worker
        await order_manager.shutdown()


@pytest.mark.asyncio
async def test_sell_spam_cap(risk_manager, mocker):
    mocker.patch("core.config.settings.DRY_RUN_MODE", True)

    with patch("core.config.settings.DRY_RUN_MODE", True):
        order_manager = OrderManager(risk_manager=risk_manager)
        order_manager.is_dry_run = True

        # Setup fake state
        order_manager.paper_ledger.balance = 10000.0
        order_manager.paper_ledger.positions["BTC/USDT"] = 0.999

        task_action = "CREATE"
        task_payload = {
            "symbol": "BTC/USDT",
            "type": "market",
            "side": "sell",
            "amount": 1.0,
            "price": 50000.0,
        }
        await order_manager.order_queue.put((task_action, task_payload))

        # Run worker for a brief moment
        task = asyncio.create_task(order_manager._process_queue())
        await asyncio.sleep(0.1)
        task.cancel()

        # Amount should have been capped to 0.999, which allows the sale
        # and reduces the position to 0 (or almost 0 due to fees)
        # Fees might slightly adjust this if balance or proceeds affect positions,
        # but the ledger subtracts the *exact* amount sold.
        # Here amount was 0.999 so it should be EXACTLY 0.0
        assert order_manager.paper_ledger.positions.get("BTC/USDT", 0.0) <= 0.001


@pytest.mark.asyncio
async def test_sell_spam_dust_threshold(risk_manager, mocker):
    mocker.patch("core.config.settings.DRY_RUN_MODE", True)

    with patch("core.config.settings.DRY_RUN_MODE", True):
        order_manager = OrderManager(risk_manager=risk_manager)
        order_manager.is_dry_run = True

        # Setup fake state with a dust position
        order_manager.paper_ledger.balance = 10000.0
        order_manager.paper_ledger.positions["BTC/USDT"] = 1e-7

        task_action = "CREATE"
        task_payload = {
            "symbol": "BTC/USDT",
            "type": "market",
            "side": "sell",
            "amount": 1.0,
            "price": 50000.0,
        }
        await order_manager.order_queue.put((task_action, task_payload))

        # Run worker for a brief moment
        task = asyncio.create_task(order_manager._process_queue())
        await asyncio.sleep(0.1)
        task.cancel()

        # Position should be wiped to 0.0 because it's considered dust
        assert order_manager.paper_ledger.positions.get("BTC/USDT", 0.0) == 0.0


@pytest.mark.asyncio
async def test_sell_spam_dust_threshold_live(risk_manager, mocker):
    mocker.patch("core.config.settings.DRY_RUN_MODE", False)

    with patch("core.config.settings.DRY_RUN_MODE", False):
        order_manager = OrderManager(risk_manager=risk_manager)
        order_manager.is_dry_run = False

        # Setup fake state with a dust position in risk manager
        await risk_manager.register_position("BTC/USDT", 50000.0, 1e-7)

        assert "BTC/USDT" in risk_manager.active_positions

        task_action = "CREATE"
        task_payload = {
            "symbol": "BTC/USDT",
            "type": "market",
            "side": "sell",
            "amount": 1.0,
            "price": 50000.0,
        }
        await order_manager.order_queue.put((task_action, task_payload))

        # Run worker for a brief moment
        task = asyncio.create_task(order_manager._process_queue())
        await asyncio.sleep(0.1)
        task.cancel()

        # Position should be wiped from risk_manager because it's considered dust
        assert "BTC/USDT" not in risk_manager.active_positions
