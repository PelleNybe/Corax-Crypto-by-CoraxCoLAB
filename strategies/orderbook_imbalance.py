import polars as pl
from core.strategy import BaseStrategy


class OrderbookImbalance(BaseStrategy):
    """
    Dummy strategy representing an Orderbook Imbalance trader.
    """

    def __init__(self):
        super().__init__()

    def populate_indicators(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df

    def populate_signals(self, df: pl.LazyFrame) -> pl.LazyFrame:
        # Dummy logic: Always recommend SELL for testing consensus
        df = df.with_columns([pl.lit(False).alias("buy"), pl.lit(True).alias("sell")])
        return df
