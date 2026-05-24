import polars as pl
from core.strategy import BaseStrategy


class SmaCrossover(BaseStrategy):
    """
    A simple Simple Moving Average (SMA) Crossover strategy.
    """

    def __init__(self):
        super().__init__()
        self.fast_window = 10
        self.slow_window = 50

    def populate_indicators(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """
        Calculates SMA fast and slow.
        """
        df = df.with_columns(
            [
                pl.col("price")
                .rolling_mean(window_size=self.fast_window)
                .alias("sma_fast"),
                pl.col("price")
                .rolling_mean(window_size=self.slow_window)
                .alias("sma_slow"),
            ]
        )
        return df

    def populate_signals(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """
        Signals BUY when fast SMA crosses above slow SMA.
        Signals SELL when fast SMA crosses below slow SMA.
        """
        df = df.with_columns(
            [
                (
                    (pl.col("sma_fast") > pl.col("sma_slow"))
                    & (pl.col("sma_fast").shift(1) <= pl.col("sma_slow").shift(1))
                )
                .fill_null(False)
                .alias("buy"),
                (
                    (pl.col("sma_fast") < pl.col("sma_slow"))
                    & (pl.col("sma_fast").shift(1) >= pl.col("sma_slow").shift(1))
                )
                .fill_null(False)
                .alias("sell"),
            ]
        )
        return df
