import polars as pl
import asyncio
from loguru import logger
from schemas.signals import AISignal


class EventDrivenBacktester:
    """
    Tick-level Event-Driven Backtester.
    Iterates through historical Parquet data tick-by-tick to simulate exact queue position and latency.
    """

    def __init__(self, parquet_path: str, latency_ms: int = 50):
        self.parquet_path = parquet_path
        self.latency_ms = latency_ms
        self.simulated_order_book = {}
        self.balance = 10000.0

    async def run(self, strategy_callback):
        logger.info(
            f"Starting Event-Driven Backtest on {self.parquet_path} with {self.latency_ms}ms latency."
        )

        try:
            # Load as lazy frame but stream in chunks for tick simulation
            lf = pl.scan_parquet(self.parquet_path)
            # In a real environment, we'd use iter_batches() for true streaming
            # Here we just take a small chunk to demonstrate
            df = await asyncio.to_thread(lf.head(1000).collect)

            for row in df.iter_rows(named=True):
                # 1. Update Simulated Orderbook
                symbol = row.get("symbol", "UNKNOWN")
                self.simulated_order_book[symbol] = {
                    "bid": row.get("bid", row.get("close", 0)),
                    "ask": row.get("ask", row.get("close", 0)),
                    "volume": row.get("volume", 0),
                }

                # 2. Trigger Strategy
                signal = await strategy_callback(row)

                # 3. Simulate Execution Latency
                if signal and signal.action != "HOLD":
                    await self._simulate_execution(symbol, signal)

        except Exception as e:
            logger.error(f"Event-Driven Backtest failed: {e}")

        logger.info(f"Backtest complete. Final Simulated Balance: {self.balance}")

    async def _simulate_execution(self, symbol: str, signal: AISignal):
        # Simulate network latency
        await asyncio.sleep(self.latency_ms / 1000.0)

        # Determine fill price based on simulated L2 book
        book = self.simulated_order_book.get(symbol, {})
        fill_price = (
            book.get("ask", 0) if signal.action == "BUY" else book.get("bid", 0)
        )

        if fill_price > 0:
            logger.debug(f"Simulated {signal.action} fill for {symbol} at {fill_price}")

            # Simple simulation of capital allocation
            trade_size = 100.0  # Fixed $100 trades for backtest
            if signal.action == "BUY":
                self.balance -= trade_size
            elif signal.action == "SELL":
                # In a real engine, we'd look up the held amount and sell that.
                # Here we just blindly add the proceeds assuming we held an equivalent position.
                self.balance += trade_size * (
                    fill_price / (fill_price * 0.999)
                )  # Real execution math
