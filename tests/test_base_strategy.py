import polars as pl
import pytest
from core.strategy import BaseStrategy


class DummyStrategy(BaseStrategy):
    """
    A simple dummy strategy to test the BaseStrategy abstract class.
    """

    def populate_indicators(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.with_columns(pl.lit(1).alias("dummy_indicator"))

    def populate_signals(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df.with_columns([pl.lit(True).alias("buy"), pl.lit(False).alias("sell")])


def test_base_strategy_initialization():
    strategy = DummyStrategy()
    assert strategy.name == "DummyStrategy"

    strategy_with_name = DummyStrategy(name="CustomName")
    assert strategy_with_name.name == "CustomName"


def test_base_strategy_populate_indicators():
    strategy = DummyStrategy()
    df = pl.LazyFrame({"price": [10.0, 12.0]})
    result_df = strategy.populate_indicators(df).collect()

    assert "dummy_indicator" in result_df.columns
    assert result_df["dummy_indicator"].to_list() == [1, 1]


def test_base_strategy_populate_signals():
    strategy = DummyStrategy()
    df = pl.LazyFrame({"price": [10.0, 12.0]})
    result_df = strategy.populate_signals(df).collect()

    assert "buy" in result_df.columns
    assert "sell" in result_df.columns
    assert result_df["buy"].to_list() == [True, True]
    assert result_df["sell"].to_list() == [False, False]


def test_base_strategy_instantiation_fails_without_abstract_methods():
    class IncompleteStrategy(BaseStrategy):
        pass

    with pytest.raises(TypeError):
        IncompleteStrategy()
