import polars as pl
import asyncio
from loguru import logger
from typing import Callable, Awaitable
from intelligence.corax_ai import CoraxAIEngine
from intelligence.regime_detector import RegimeDetector
from schemas.signals import AISignal


class MarketDataStream:
    """
    MarketDataStream processes incoming websocket ticks into highly optimized LazyFrames
    in real-time. Designed for High-Frequency Trading (HFT) and zero-copy data manipulation.
    """

    def __init__(
        self,
        ai_engine: CoraxAIEngine,
        regime_detector: RegimeDetector,
        buffer_size: int = 1000,
        on_signal_callback: Callable[[AISignal, str], Awaitable[None]] = None,
    ):
        from core.strategy_loader import load_strategy

        self.buffer_size = buffer_size
        self._buffer = []
        # Maintain a rolling window of max 10,000 ticks for context
        self._history = []
        self._max_history = 10000

        self._schema = {
            "symbol": pl.String,
            "timestamp": pl.Int64,
            "price": pl.Float64,
            "volume": pl.Float64,
            "side": pl.String,
        }
        self.ai_engine = ai_engine
        self.regime_detector = regime_detector
        self.on_signal_callback = on_signal_callback

        try:
            self.strategy = load_strategy()
        except Exception as e:
            logger.error(
                f"Failed to load dynamic strategy: {e}. AI engine will operate stand-alone."
            )
            self.strategy = None

    async def process_tick(self, tick: dict):
        try:
            self._buffer.append(tick)

            if len(self._buffer) >= self.buffer_size:
                await self._flush_buffer()
        except KeyError as e:
            logger.error(f"Missing expected field in tick: {e}")

    async def _flush_buffer(self):
        if not self._buffer:
            return

        if self._buffer:
            keys = self._buffer[0].keys()
            columnar_data = {k: [d.get(k) for d in self._buffer] for k in keys}
            df = pl.DataFrame(columnar_data, schema=self._schema)  # noqa: F841

        # Append to history and truncate
        self._history.extend(self._buffer)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        self._buffer.clear()

        # Build lazyframe from full history for continuous context
        keys_hist = self._history[0].keys()
        columnar_hist = {k: [d.get(k) for d in self._history] for k in keys_hist}
        history_df = pl.DataFrame(columnar_hist, schema=self._schema)

        lazy_df = (
            history_df.lazy()
            .with_columns((pl.col("price") * pl.col("volume")).alias("notional_value"))
            .filter(pl.col("volume") > 0)
        )

        asyncio.create_task(self._dispatch_to_strategies(lazy_df))

    async def _dispatch_to_strategies(self, lazy_df: pl.LazyFrame):
        try:
            regime = await self.regime_detector.detect_regime(lazy_df)

            # Apply dynamic modular strategy if available
            strategy_signal = "HOLD"
            if self.strategy:
                # Polars requires await if we were pushing this off-thread, but for LazyFrames
                # we just build the graph then collect it.
                lazy_df = self.strategy.populate_indicators(lazy_df)
                lazy_df = self.strategy.populate_signals(lazy_df)

                # We need to collect here to check the last signal.
                # STRICT DIRECTIVE: Use await asyncio.to_thread for .collect()
                df = await asyncio.to_thread(lazy_df.collect)

                if df.height > 0:
                    last_row = df[-1]
                    if "buy" in df.columns and last_row["buy"][0]:
                        strategy_signal = "BUY"
                    elif "sell" in df.columns and last_row["sell"][0]:
                        strategy_signal = "SELL"

            else:
                df = await asyncio.to_thread(lazy_df.collect)

            # The AI engine provides an overarching synthesis/signal
            signal = await self.ai_engine.analyze_market_state(df, regime=regime)

            # Override AI action if modular strategy has a strong deterministic signal
            if self.strategy and strategy_signal != "HOLD":
                signal.action = strategy_signal
                signal.reasoning = (
                    f"[{self.strategy.name}] Condition met in regime {regime}."
                )
                signal.confidence_score = 1.0

            logger.info(f"Generated Signal in regime {regime}: {signal}")

            if self.on_signal_callback:
                asyncio.create_task(self.on_signal_callback(signal, regime))
        except Exception as e:
            logger.error(f"Error during strategy dispatch: {e}")
