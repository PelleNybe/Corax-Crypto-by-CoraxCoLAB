import polars as pl
from core.strategy import BaseStrategy


class StatisticalArbitrage(BaseStrategy):
    """
    World-Class Feature 1: Statistical Arbitrage (Z-Score Mean Reversion)
    Calculates the rolling Z-Score of the price (or spread) to identify
    statistically significant deviations from the mean.
    """

    def __init__(self):
        super().__init__()
        self.rolling_window = 100
        self.z_score_threshold_buy = -2.0
        self.z_score_threshold_sell = 2.0

    def populate_indicators(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """
        Calculates the rolling mean, rolling standard deviation, and the Z-Score.
        """
        df = df.with_columns(
            [
                pl.col("price")
                .rolling_mean(window_size=self.rolling_window)
                .alias("rolling_mean"),
                pl.col("price")
                .rolling_std(window_size=self.rolling_window)
                .alias("rolling_std"),
            ]
        )

        # Calculate Z-Score: (Price - Rolling Mean) / Rolling Std Dev
        df = df.with_columns(
            ((pl.col("price") - pl.col("rolling_mean")) / pl.col("rolling_std"))
            .fill_null(0.0)
            .alias("z_score")
        )
        return df

    def populate_signals(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """
        Signals BUY when Z-Score crosses below the negative threshold (oversold).
        Signals SELL when Z-Score crosses above the positive threshold (overbought).
        """
        df = df.with_columns(
            [
                (
                    (pl.col("z_score") < self.z_score_threshold_buy)
                    & (pl.col("z_score").shift(1) >= self.z_score_threshold_buy)
                )
                .fill_null(False)
                .alias("buy"),
                (
                    (pl.col("z_score") > self.z_score_threshold_sell)
                    & (pl.col("z_score").shift(1) <= self.z_score_threshold_sell)
                )
                .fill_null(False)
                .alias("sell"),
            ]
        )
        return df
