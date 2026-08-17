import polars as pl
import asyncio
from typing import Dict, Any
from core.strategy import BaseStrategy
from loguru import logger
import time

from intelligence.metrics import (
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_win_loss_ratio,
)


class VectorizedBacktester:
    """
    High-Velocity Backtesting Engine using purely vectorized Polars operations.
    Designed to process historical Parquet files and apply strategies without Pandas or slow Python loops.
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.001,
    ):
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate

    async def run(self, data_path: str) -> Dict[str, Any]:
        logger.info(
            f"Starting Vectorized Backtest for {self.strategy.name} on {data_path}"
        )
        start_time = time.time()

        # Load data lazily
        try:
            lazy_df = pl.scan_parquet(data_path)
        except Exception as e:
            logger.error(f"Failed to scan parquet file {data_path}: {e}")
            raise

        # Apply strategy logic
        lazy_df = self.strategy.populate_indicators(lazy_df)
        lazy_df = self.strategy.populate_signals(lazy_df)

        # Strict Directive: Blocking .collect() must be wrapped in to_thread
        try:
            df = await asyncio.to_thread(lazy_df.collect)
        except Exception as e:
            logger.error(f"Failed to collect Polars DataFrame: {e}")
            raise

        # Pure Vectorized Backtesting Logic
        # Create a signal column: 1 for buy, -1 for sell, 0 otherwise
        df = df.with_columns(
            pl.when(pl.col("sell"))
            .then(pl.lit(-1))
            .when(pl.col("buy"))
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .alias("signal")
        )

        # Filter to only rows where a signal is present
        signals_df = df.filter(pl.col("signal") != 0)

        current_capital = self.initial_capital
        returns = []
        equity_curve = [self.initial_capital]

        if signals_df.height > 0:
            # Keep only rows where signal changes (prevent multiple buys/sells in a row)
            signals_df = signals_df.filter(
                pl.col("signal") != pl.col("signal").shift(1).fill_null(0)
            )

            # Ensure the sequence starts with a buy
            if signals_df.height > 0 and signals_df["signal"][0] == -1:
                signals_df = signals_df.slice(1)

            # Ensure the sequence ends with a sell
            if signals_df.height > 0 and signals_df["signal"][-1] == 1:
                signals_df = signals_df.slice(0, signals_df.height - 1)

        if signals_df.height >= 2:
            buys = signals_df.filter(pl.col("signal") == 1)
            sells = signals_df.filter(pl.col("signal") == -1)

            # Calculate returns for each paired trade
            buy_prices = buys["price"]
            sell_prices = sells["price"]

            # Multiplier for each trade factoring in fee rate on entry and exit
            multipliers = (sell_prices / buy_prices) * ((1 - self.fee_rate) ** 2)
            trade_returns = multipliers - 1

            returns = trade_returns.to_list()

            # Cumulative product for equity curve
            equity_curve_series = multipliers.cum_prod() * self.initial_capital
            current_capital = equity_curve_series[-1]
            equity_curve.extend(equity_curve_series.to_list())

        # Calculate Metrics
        returns_series = pl.Series("returns", returns)
        equity_series = pl.Series("equity", equity_curve)

        sharpe = calculate_sharpe_ratio(returns_series)
        max_dd = calculate_max_drawdown(equity_series)
        win_loss = calculate_win_loss_ratio(returns_series)

        total_return = (
            (current_capital - self.initial_capital) / self.initial_capital
        ) * 100

        metrics = {
            "strategy": self.strategy.name,
            "total_trades": len(returns),
            "initial_capital": self.initial_capital,
            "final_capital": current_capital,
            "total_return_pct": total_return,
            "win_loss_ratio": win_loss,
            "max_drawdown_pct": max_dd * 100,
            "sharpe_ratio": sharpe,
            "execution_time_sec": time.time() - start_time,
        }

        logger.info(f"Vectorized Backtest completed: {metrics}")
        return metrics
