import pytest


@pytest.mark.asyncio
async def test_exchange_manager_initialization():
    from core.config import settings

    # We must patch ccxt module that the manager imports
    class MockCCXTExchange:
        def __init__(self, config):
            self.id = "mock"
            self.has = {"watchTrades": True, "createMarketOrder": True}
            self.options = config.get("options", {})

        async def load_markets(self):
            self.markets = {
                "BTC/USDT": {"symbol": "BTC/USDT", "type": "spot"},
                "BTC/USDT:USDT": {
                    "symbol": "BTC/USDT:USDT",
                    "type": "future",
                    "linear": True,
                },
            }

        async def set_leverage(self, leverage, symbol):
            pass

        async def close(self):
            pass

    # Patch the real ccxtpro module that the file imports
    from unittest.mock import patch

    with patch("execution.exchange_manager.ccxtpro") as mock_ccxtpro:
        mock_ccxtpro.binance = MockCCXTExchange
        import ccxt

        mock_ccxtpro.errors = ccxt.errors

        # Re-import to ensure it picks up the mock, or just reset state
        import execution.exchange_manager as em

        em.exchange_manager._initialized = False  # force re-init
        em.exchange_manager.exchanges = {}

        # Override settings before calling initialize
        settings.EXCHANGE_ID = "binance"
        settings.ARBITRAGE_EXCHANGES = []  # Don't load defaults
        settings.COPY_TRADE_ENABLED = True
        settings.MULTI_ACCOUNT_CONFIG = '{"acc1": {"exchange": "binance", "apiKey": "x", "secret": "y", "market_type": "future", "leverage": 10}}'

        await em.exchange_manager.initialize()

        assert "binance_acc1" in em.exchange_manager.exchanges
        # assert "binance" in em.exchange_manager.exchanges


@pytest.mark.asyncio
async def test_execute_order_with_context():
    from schemas.orders import OrderContext
    from unittest.mock import AsyncMock
    import execution.exchange_manager as em

    em.exchange_manager.exchanges = {"binance": AsyncMock()}

    em.exchange_manager.exchanges["binance"].create_order = AsyncMock(
        return_value={"id": "123", "status": "open"}
    )

    context = OrderContext(
        symbol="BTC/USDT",
        side="buy",
        amount=1.5,
        order_type="limit",
        current_price=50000.0,
    )

    result = await em.exchange_manager.execute_order("binance", context)

    assert result == {"id": "123", "status": "open"}
    em.exchange_manager.exchanges["binance"].create_order.assert_called_once_with(
        "BTC/USDT", "limit", "buy", 1.5, 50000.0, {}
    )
