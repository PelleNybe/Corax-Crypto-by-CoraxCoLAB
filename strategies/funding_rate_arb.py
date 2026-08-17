import polars as pl
from core.strategy import BaseStrategy


class FundingRateArb(BaseStrategy):
    """
    Implements Funding Rate Arbitrage trading signals based on rate divergence.
    """

    def __init__(self):
        super().__init__()
        self.funding_rate_threshold = 0.001  # Example threshold

    def populate_indicators(self, df: pl.LazyFrame) -> pl.LazyFrame:
        # In a fully functional strategy, we would ingest funding rate data from
        # the exchange or GlobalState. For this strategy implementation within Polars,
        # we calculate proxy indicators if actual funding rate is not in columns.

        if "funding_rate" not in df.columns:
            # Proxy: Assuming if price is significantly above a long-term MA, funding rate might be positive
            df = df.with_columns(
                [pl.col("price").rolling_mean(window_size=200).alias("price_ma_200")]
            )
            df = df.with_columns(
                [
                    (
                        (pl.col("price") - pl.col("price_ma_200"))
                        / pl.col("price_ma_200")
                        * 0.01
                    ).alias("funding_rate_proxy")
                ]
            )
        else:
            df = df.with_columns([pl.col("funding_rate").alias("funding_rate_proxy")])

        return df

    def populate_signals(self, df: pl.LazyFrame) -> pl.LazyFrame:
        # Generate signals: If funding rate is highly positive, we might short (sell),
        # if highly negative, we might long (buy).
        df = df.with_columns(
            [
                (pl.col("funding_rate_proxy") < -self.funding_rate_threshold).alias(
                    "buy"
                ),
                (pl.col("funding_rate_proxy") > self.funding_rate_threshold).alias(
                    "sell"
                ),
            ]
        )
        return df
