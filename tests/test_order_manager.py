import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
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
        mocker.patch(
            "core.arc_ledger.requests.get",
            return_value=MagicMock(
                status_code=200,
                json=lambda: {
                    "data": {"balances": [{"currency": "USD", "amount": "10000.0"}]}
                },
            ),
        )
        mocker.patch(
            "core.arc_ledger.requests.post",
            return_value=MagicMock(status_code=200, json=lambda: {}),
        )

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
        order_manager.paper_ledger.execute_virtual_order.assert_called_once()

        # Shutdown worker
        await order_manager.shutdown()
