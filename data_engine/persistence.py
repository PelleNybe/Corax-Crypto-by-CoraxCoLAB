import polars as pl
import asyncio
import os
import time
from loguru import logger
from execution.exchange_manager import exchange_manager


class TickLogger:
    """
    High-Speed Data Persistence logger.
    Buffers incoming trade ticks from the Unified Exchange Manager
    and flushes them to partitioned .parquet files using Polars.
    Parquet provides efficient, compressed storage universally compatible across Linux systems.
    """

    def __init__(self, data_dir: str = "data/ticks", buffer_size: int = 1000):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self._lock = asyncio.Lock()

        self.buffer_size = buffer_size
        self._buffer = []
        self._schema = {
            "symbol": pl.String,
            "timestamp": pl.Int64,
            "price": pl.Float64,
            "volume": pl.Float64,
            "side": pl.String,
            "exchange": pl.String,
        }

        # Subscribe to trades stream from exchange manager
        self.trade_queue = exchange_manager.subscribe_trades()
        self._worker_task = asyncio.create_task(self._process_trades())

    async def _process_trades(self):
        """Background worker that pulls from the shared trade queue and buffers them."""
        logger.info("TickLogger subscribed to unified trades stream.")
        try:
            while True:
                trade_event = await self.trade_queue.get()
                exchange_id = trade_event["exchange_id"]
                symbol = trade_event["symbol"]
                trades = trade_event["data"]

                for t in trades:
                    # Performance optimization: using tuples instead of dicts for faster DataFrame initialization
                    try:
                        tick = (
                            symbol,
                            t["timestamp"]
                            if "timestamp" in t
                            else int(time.time() * 1000),
                            float(t["price"]) if "price" in t else 0.0,
                            float(t["amount"]) if "amount" in t else 0.0,
                            t["side"] if "side" in t else "unknown",
                            exchange_id,
                        )
                    except KeyError:
                        tick = (
                            symbol,
                            t.get("timestamp", int(time.time() * 1000)),
                            float(t.get("price", 0.0)),
                            float(t.get("amount", 0.0)),
                            t.get("side", "unknown"),
                            exchange_id,
                        )
                    self._buffer.append(tick)

                if len(self._buffer) >= self.buffer_size:
                    await self._flush_buffer()

        except asyncio.CancelledError:
            logger.info(
                "TickLogger background worker cancelled. Flushing remaining ticks..."
            )
            await self._flush_buffer()
        except Exception as e:
            logger.error(f"Error in TickLogger _process_trades: {e}")

    async def _flush_buffer(self):
        """Flushes buffered ticks to disk."""
        if not self._buffer:
            return

        async with self._lock:
            # Create a clone of the buffer to allow new ticks while we write
            buffer_copy = list(self._buffer)
            self._buffer.clear()

            # Performance optimization: orient='row' with tuple lists avoids slow python-level dictionary unpacking
            df = pl.DataFrame(
                buffer_copy, schema=list(self._schema.keys()), orient="row"
            )
            # Chain cast operations for optimal typed initialization
            df = df.cast(self._schema)
            # Polars I/O blocking call must be dispatched to thread
            await asyncio.to_thread(self._write_parquet_blocking, df)

    def _write_parquet_blocking(self, df: pl.DataFrame):
        """Synchronous parquet writing method."""
        if df.height == 0:
            return

        timestamp = int(time.time() * 1000)
        filename = f"{self.data_dir}/ticks_{timestamp}.parquet"
        try:
            df.write_parquet(filename)
            logger.debug(f"Flushed {df.height} ticks to {filename}")
        except Exception as e:
            logger.error(f"Failed to write parquet file {filename}: {e}")

    async def shutdown(self):
        """Clean shutdown and unsubscribe."""
        if self._worker_task:
            self._worker_task.cancel()
        await exchange_manager.unsubscribe_trades(self.trade_queue)
