import polars as pl
from strategies.sma_crossover import SmaCrossover


def test_populate_indicators():
    strategy = SmaCrossover()
    strategy.fast_window = 2
    strategy.slow_window = 3

    # Create mock LazyFrame
    df = pl.LazyFrame({"price": [10.0, 12.0, 14.0, 16.0, 18.0]})

    result_df = strategy.populate_indicators(df).collect()

    # Check if 'sma_fast' and 'sma_slow' columns are added
    assert "sma_fast" in result_df.columns
    assert "sma_slow" in result_df.columns

    # Verify values
    sma_fast = result_df["sma_fast"].to_list()
    # fast=2 -> [None, 11.0, 13.0, 15.0, 17.0]
    assert sma_fast[0] is None
    assert sma_fast[1] == 11.0
    assert sma_fast[2] == 13.0
    assert sma_fast[3] == 15.0
    assert sma_fast[4] == 17.0

    sma_slow = result_df["sma_slow"].to_list()
    # slow=3 -> [None, None, 12.0, 14.0, 16.0]
    assert sma_slow[0] is None
    assert sma_slow[1] is None
    assert sma_slow[2] == 12.0
    assert sma_slow[3] == 14.0
    assert sma_slow[4] == 16.0


def test_populate_signals():
    strategy = SmaCrossover()

    # Create mock LazyFrame with pre-populated indicators
    # We want a crossover to happen
    # fast crosses above slow: (fast > slow) and (fast_prev <= slow_prev)
    # fast crosses below slow: (fast < slow) and (fast_prev >= slow_prev)
    df = pl.LazyFrame(
        {
            "price": [1.0, 2.0, 3.0, 4.0, 5.0],
            "sma_fast": [10.0, 10.0, 12.0, 8.0, 8.0],
            "sma_slow": [12.0, 11.0, 11.0, 10.0, 7.0],
        }
    )

    result_df = strategy.populate_signals(df).collect()

    assert "buy" in result_df.columns
    assert "sell" in result_df.columns

    buy_signals = result_df["buy"].to_list()
    sell_signals = result_df["sell"].to_list()

    # Row 0: fast=10, slow=12 (fast <= slow, fast_prev = null -> null -> fill_null(False) -> False)
    # Row 1: fast=10, slow=11 (fast <= slow, fast_prev = 10 <= 12 -> False)
    # Row 2: fast=12, slow=11 (fast > slow, fast_prev = 10 <= 11 -> True)
    # Row 3: fast=8, slow=10 (fast < slow, fast_prev = 12 >= 11 -> True sell)
    # Row 4: fast=8, slow=7 (fast > slow, fast_prev = 8 <= 10 -> True buy)

    assert buy_signals == [False, False, True, False, True]
    assert sell_signals == [False, False, False, True, False]
