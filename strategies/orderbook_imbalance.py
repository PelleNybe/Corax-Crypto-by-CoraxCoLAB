import polars as pl
from core.strategy import BaseStrategy


class OrderbookImbalance(BaseStrategy):
    """
    Implements Orderbook Imbalance (OFI) based trading signals.
    """

    def __init__(self):
        super().__init__()
        self.imbalance_threshold = 0.2  # 20% imbalance

    def populate_indicators(self, df: pl.LazyFrame) -> pl.LazyFrame:
        # Calculate Order Flow Imbalance if volume and side data exists
        if "volume" in df.columns and "side" in df.columns:
            # This is a simplified OFI calculation for tick data
            df = df.with_columns(
                [
                    pl.when(pl.col("side") == "buy")
                    .then(pl.col("volume"))
                    .otherwise(-pl.col("volume"))
                    .alias("signed_volume")
                ]
            )
            # Calculate rolling sum of signed volume as OFI
            df = df.with_columns(
                [pl.col("signed_volume").rolling_sum(window_size=50).alias("ofi")]
            )
            # Normalize OFI by total volume
            df = df.with_columns(
                [pl.col("volume").rolling_sum(window_size=50).alias("total_vol_50")]
            )
            df = df.with_columns(
                [(pl.col("ofi") / pl.col("total_vol_50")).alias("ofi_ratio")]
            )
        else:
            # Fallback if specific tick data is missing
            df = df.with_columns([pl.lit(0.0).alias("ofi_ratio")])

        return df

    def populate_signals(self, df: pl.LazyFrame) -> pl.LazyFrame:
        # Generate signals based on OFI ratio
        df = df.with_columns(
            [
                (pl.col("ofi_ratio") > self.imbalance_threshold).alias("buy"),
                (pl.col("ofi_ratio") < -self.imbalance_threshold).alias("sell"),
            ]
        )
        return df
