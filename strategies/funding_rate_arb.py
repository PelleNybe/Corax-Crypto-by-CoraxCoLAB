import polars as pl
from core.strategy import BaseStrategy


class FundingRateArb(BaseStrategy):
    """
    Dummy strategy representing a Funding Rate Arbitrage trader.
    """

    def __init__(self):
        super().__init__()

    def populate_indicators(self, df: pl.LazyFrame) -> pl.LazyFrame:
        return df

    def populate_signals(self, df: pl.LazyFrame) -> pl.LazyFrame:
        # Dummy logic: Always recommend BUY for testing consensus
        df = df.with_columns([pl.lit(True).alias("buy"), pl.lit(False).alias("sell")])
        return df
