import pytest
import os
import asyncio

# Set required environment variables BEFORE importing config
os.environ["EXCHANGE_API_KEY"] = "test"
os.environ["EXCHANGE_API_SECRET"] = "test"
os.environ["LLM_API_KEY"] = "test"
os.environ["CORAX_MODE"] = "testnet"

from core.config import settings
from strategies.grid_trading import GridTrading
from execution.order_manager import OrderManager
from core.risk_manager import RiskManager
import pytest_asyncio


@pytest.fixture
def grid_strategy():
    settings.GRID_UPPER_PRICE = 60000.0
    settings.GRID_LOWER_PRICE = 40000.0
    settings.GRID_LEVELS = 3
    return GridTrading()


def test_grid_generation(grid_strategy):
    # Should generate: 40k, 50k, 60k
    lines = grid_strategy.generate_grid(current_price=51000.0, total_investment=3000.0)

    assert len(lines) == 3
    assert lines[0]["price"] == 40000.0
    assert lines[0]["side"] == "buy"  # Below 51k

    assert lines[1]["price"] == 50000.0
    assert lines[1]["side"] == "buy"  # Below 51k

    assert lines[2]["price"] == 60000.0
    assert lines[2]["side"] == "sell"  # Above 51k

    # 3000 / 3 = 1000 quote per line. Base amount = 1000 / 51000 = ~0.0196
    assert round(lines[0]["amount"], 4) == 0.0196


@pytest_asyncio.fixture
async def mock_om():
    rm = RiskManager()
    om = OrderManager(rm)
    om.order_queue = asyncio.Queue()
    return om


@pytest.mark.asyncio
async def test_grid_deployment(mock_om, grid_strategy):
    lines = grid_strategy.generate_grid(current_price=50000.0, total_investment=3000.0)
    await mock_om.initialize_grid("BTC/USDT", 50000.0, 3000.0, lines)

    assert "BTC/USDT" in mock_om.active_grids
    state = mock_om.active_grids["BTC/USDT"]
    assert len(state.lines) == 3

    # Verify queue was populated with creates
    assert mock_om.order_queue.qsize() == 3

    action, payload = await mock_om.order_queue.get()
    assert action == "CREATE"
    assert payload["type"] == "limit"
    assert payload["price"] == 40000.0
