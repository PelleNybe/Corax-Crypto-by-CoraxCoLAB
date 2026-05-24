import asyncio
import polars as pl
from loguru import logger
from typing import List, Dict
import time
import os

from intelligence.corax_ai import CoraxAIEngine
from intelligence.regime_detector import RegimeDetector
from schemas.signals import AISignal
from intelligence.metrics import (
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_win_loss_ratio,
)


class CoraxBacktester:
    """
    High-Velocity Backtesting Engine.
    Uses Polars lazy execution to stream historical parquet data.
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.001,
        slippage: float = 0.0005,
    ):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage = slippage

        self.ai_engine = CoraxAIEngine()
        self.regime_detector = RegimeDetector(ai_backend=self.ai_engine.fast_backend)

        self.trades: List[Dict] = []
        self.equity_curve: List[float] = [initial_capital]
        self.position = 0.0
        self.avg_entry_price = 0.0

    def load_historical_data(self, path: str) -> pl.LazyFrame:
        logger.info(f"Scanning historical data from: {path}")
        return pl.scan_parquet(path)

    async def _simulate_execution(
        self, signal: AISignal, current_price: float, timestamp: int
    ):
        if signal.action == "BUY" and self.current_capital > 0:
            exec_price = current_price * (1 + self.slippage)
            trade_value = self.current_capital * 0.10
            fee = trade_value * self.fee_rate
            amount_bought = (trade_value - fee) / exec_price

            self.current_capital -= trade_value
            self.position += amount_bought
            self.avg_entry_price = exec_price

            self.trades.append(
                {
                    "timestamp": timestamp,
                    "action": "BUY",
                    "price": exec_price,
                    "amount": amount_bought,
                    "fee": fee,
                    "return": 0.0,
                }
            )

        elif signal.action == "SELL" and self.position > 0:
            exec_price = current_price * (1 - self.slippage)
            trade_value = self.position * exec_price
            fee = trade_value * self.fee_rate
            net_proceeds = trade_value - fee
            trade_return = (exec_price - self.avg_entry_price) / self.avg_entry_price

            self.current_capital += net_proceeds
            self.position = 0.0

            self.trades.append(
                {
                    "timestamp": timestamp,
                    "action": "SELL",
                    "price": exec_price,
                    "amount": self.position,
                    "fee": fee,
                    "return": trade_return,
                }
            )

            self.equity_curve.append(self.current_capital)

    async def run_simulation(self, data_path: str, chunk_size: int = 1000):
        logger.info("Starting Backtest Simulation...")
        start_time = time.time()

        lazy_df = self.load_historical_data(data_path)

        try:
            df = await asyncio.to_thread(lazy_df.collect, streaming=True)

            for i in range(0, df.height, chunk_size):
                chunk = df.slice(i, chunk_size)
                if chunk.height == 0:
                    break

                chunk_lazy = chunk.lazy()
                current_price = chunk["price"][-1]
                current_timestamp = chunk["timestamp"][-1]

                regime = await self.regime_detector.detect_regime(chunk_lazy)
                signal = await self.ai_engine.analyze_market_state(
                    chunk_lazy, regime=regime
                )

                if signal.action in ["BUY", "SELL"]:
                    await self._simulate_execution(
                        signal, current_price, current_timestamp
                    )

        except Exception as e:
            logger.error(f"Error during simulation: {e}")

        self._generate_report(start_time)

    def _generate_report(self, start_time: float):
        elapsed_time = time.time() - start_time

        if not self.trades:
            logger.info("No trades executed during simulation.")
            return

        if self.position > 0:
            final_price = self.trades[-1]["price"]
            self.current_capital += self.position * final_price

        trades_df = pl.DataFrame(self.trades)
        equity_series = pl.Series(self.equity_curve)

        sell_trades = trades_df.filter(pl.col("action") == "SELL")
        if sell_trades.height > 0:
            returns_series = sell_trades["return"]
            sharpe = calculate_sharpe_ratio(returns_series)
            max_dd = calculate_max_drawdown(equity_series)
            win_loss = calculate_win_loss_ratio(returns_series)
        else:
            sharpe, max_dd, win_loss = 0.0, 0.0, 0.0

        total_return = (
            (self.current_capital - self.initial_capital) / self.initial_capital * 100
        )

        print("\n" + "=" * 50)
        print("📊 CORAX CRYPTO - BACKTEST REPORT 📊")
        print("=" * 50)
        print(f"Total Trades:     {len(self.trades)}")
        print(f"Initial Capital:  ${self.initial_capital:,.2f}")
        print(f"Final Capital:    ${self.current_capital:,.2f}")
        print(f"Total Return:     {total_return:,.2f}%")
        print(f"Win/Loss Ratio:   {win_loss:.2f}")
        print(f"Max Drawdown:     {max_dd * 100:.2f}%")
        print(f"Sharpe Ratio:     {sharpe:.2f}")
        print(f"Time Taken:       {elapsed_time:.2f} seconds")
        print("=" * 50)

        os.makedirs("data/reports", exist_ok=True)
        report_path = f"data/reports/backtest_{int(time.time())}.parquet"
        trades_df.write_parquet(report_path)
        logger.info(f"Detailed trade log saved to {report_path}")


if __name__ == "__main__":
    os.makedirs("data/ticks", exist_ok=True)
    test_file = "data/ticks/mock_history.parquet"
    if not os.path.exists(test_file):
        pl.DataFrame(
            {
                "symbol": ["BTC/USDT"] * 5000,
                "timestamp": range(1600000000, 1600005000),
                "price": [
                    50000.0 + (i % 100) * (1 if i % 200 < 100 else -1)
                    for i in range(5000)
                ],
                "volume": [1.0] * 5000,
                "side": ["buy"] * 5000,
            }
        ).write_parquet(test_file)

    backtester = CoraxBacktester()
    asyncio.run(backtester.run_simulation(test_file))
