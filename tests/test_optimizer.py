import pytest
import os
import polars as pl
from intelligence.optimizer import CoraxOptimizer
from strategies.sma_crossover import SmaCrossover


@pytest.fixture
def mock_data_path(tmp_path):
    path = tmp_path / "mock_history.parquet"
    # Create simple trending data
    df = pl.DataFrame(
        {
            "symbol": ["BTC/USDT"] * 500,
            "timestamp": range(1600000000, 1600000500),
            "price": [50000.0 + i * 10 for i in range(250)]
            + [52500.0 - i * 10 for i in range(250)],
            "volume": [1.0] * 500,
            "side": ["buy"] * 500,
        }
    )
    df.write_parquet(path)
    return str(path)


@pytest.mark.asyncio
async def test_optimizer_evaluation(mock_data_path):
    opt = CoraxOptimizer(population_size=2, generations=1)

    param_space = {"fast_window": (5, 20, "int"), "slow_window": (21, 50, "int")}

    best = await opt.optimize(
        SmaCrossover, param_space, mock_data_path, save_path="config/test_params.json"
    )

    assert best is not None
    assert "fast_window" in best
    assert "slow_window" in best

    # Cleanup
    if os.path.exists("config/test_params.json"):
        os.remove("config/test_params.json")
