import polars as pl
import asyncio
import glob
from loguru import logger
from data_engine.pipeline import MarketDataStream
from intelligence.corax_ai import CoraxAIEngine
from intelligence.regime_detector import RegimeDetector
from schemas.signals import AISignal


class BacktestEngine:
    def __init__(self, data_dir: str = "data/ticks"):
        self.data_dir = data_dir
        self.ai_engine = CoraxAIEngine()
        self.regime_detector = RegimeDetector(ai_backend=self.ai_engine.fast_backend)
        self.signals_generated = []

        async def _collect_signal_callback(signal: AISignal, regime: str):
            self.signals_generated.append({"signal": signal, "regime": regime})
            logger.info(
                f"[BACKTEST] Signal: {signal.action} at {signal.timestamp} (Regime: {regime})"
            )

        self.stream = MarketDataStream(
            ai_engine=self.ai_engine,
            regime_detector=self.regime_detector,
            buffer_size=100,
            on_signal_callback=_collect_signal_callback,
        )

    async def run(self):
        logger.info(f"Starting Backtest Engine. Reading from {self.data_dir}...")
        parquet_files = glob.glob(f"{self.data_dir}/*.parquet")
        if not parquet_files:
            logger.warning(
                f"No parquet files found in {self.data_dir}. Run live mode first to collect data."
            )
            return

        parquet_files.sort()

        for file in parquet_files:
            logger.info(f"Processing {file}...")
            # We use scan_parquet for lazy evaluation
            lazy_df = pl.scan_parquet(file)

            # Since MarketDataStream expects stringified JSON ticks to simulate live feed,
            # we will iterate through the rows. In a highly optimized backtest we would
            # feed the lazy_df directly to the strategies, but to test the full pipeline
            # we simulate ticks.
            df = await asyncio.to_thread(lazy_df.collect)

            for row in df.iter_rows(named=True):
                tick = {
                    "symbol": row["symbol"],
                    "timestamp": row["timestamp"],
                    "price": row["price"],
                    "volume": row["volume"],
                    "side": row["side"],
                }
                await self.stream.process_tick(tick)

        # Flush any remaining buffer
        await self.stream._flush_buffer()

        # Add a tiny sleep to allow callbacks to finish
        await asyncio.sleep(0.5)
        logger.info(
            f"Backtest complete. Total signals generated: {len(self.signals_generated)}"
        )
        return self.signals_generated


if __name__ == "__main__":
    engine = BacktestEngine()
    asyncio.run(engine.run())
