import polars as pl
import asyncio
import time
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
        from core.state import global_state

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
        self.global_state = global_state

        # World-Class Feature 3: Liquidity Velocity Circuit Breaker Parameters
        self.velocity_window = 50
        self.max_negative_velocity = -50.0  # Threshold for rapid price/liquidity drop

        try:
            self.strategy = load_strategy()
        except Exception as e:
            logger.error(
                f"Failed to load dynamic strategy: {e}. AI engine will operate stand-alone."
            )
            self.strategy = None

    async def process_tick(self, tick: dict):
        try:
            # Performance optimization: storing data as tuple for faster DataFrame init
            try:
                tick_tuple = (
                    tick["symbol"] if "symbol" in tick else "UNKNOWN",
                    tick["timestamp"]
                    if "timestamp" in tick
                    else int(time.time() * 1000),
                    float(tick["price"]) if "price" in tick else 0.0,
                    float(tick["volume"]) if "volume" in tick else 0.0,
                    tick["side"] if "side" in tick else "unknown",
                )
            except KeyError:
                tick_tuple = (
                    tick.get("symbol", "UNKNOWN"),
                    tick.get("timestamp", int(time.time() * 1000)),
                    float(tick.get("price", 0.0)),
                    float(tick.get("volume", 0.0)),
                    tick.get("side", "unknown"),
                )
            self._buffer.append(tick_tuple)

            if len(self._buffer) >= self.buffer_size:
                await self._flush_buffer()
        except KeyError as e:
            logger.error(f"Missing expected field in tick: {e}")

    async def _flush_buffer(self):
        if not self._buffer:
            return

        if self._buffer:
            # Performance optimization: orient='row' avoiding python dictionary unpacking overhead
            _df = pl.DataFrame(
                self._buffer, schema=list(self._schema.keys()), orient="row"
            ).cast(self._schema)  # noqa: F841

        # Append to history and truncate
        self._history.extend(self._buffer)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        self._buffer.clear()

        # Build lazyframe from full history for continuous context
        # Performance optimization: orient='row' avoiding python dictionary unpacking overhead
        history_df = pl.DataFrame(
            self._history, schema=list(self._schema.keys()), orient="row"
        ).cast(self._schema)

        lazy_df = (
            history_df.lazy()
            .with_columns((pl.col("price") * pl.col("volume")).alias("notional_value"))
            .filter(pl.col("volume") > 0)
        )

        asyncio.create_task(self._dispatch_to_strategies(lazy_df))

    async def _check_circuit_breaker(self, df: pl.DataFrame):
        """
        World-Class Feature 3: Liquidity Velocity Circuit Breaker
        Calculates the velocity of price changes over a short window.
        If velocity is highly negative, triggers a protective halt.
        """
        if df.height < self.velocity_window:
            return False

        # Calculate Price Velocity: (Current Price - Price N periods ago)
        current_price = df["price"][-1]
        past_price = df["price"][-self.velocity_window]
        velocity = current_price - past_price

        # Update global state for UI visualization
        await self.global_state.update_metric("liquidity_velocity", velocity)

        if velocity < self.max_negative_velocity:
            logger.critical(
                f"🛑 CIRCUIT BREAKER TRIGGERED: Extreme negative velocity ({velocity:.2f}) detected!"
            )
            # In a full implementation, this would interact directly with RiskManager
            # For now, we signal a hard halt.
            return True
        return False

    async def _dispatch_to_strategies(self, lazy_df: pl.LazyFrame):
        try:
            # PERFORMANCE OPTIMIZATION: Concurrently run regime detection and dataframe collection
            # 💡 What: Used asyncio.gather to parallelize regime detection and Polars dataframe collection.
            # 🎯 Why: Both operations are independent but await sequentially, causing an unnecessary I/O bottleneck.
            # 📊 Impact: Reduces blocking time in the critical hot path by executing both operations in parallel.
            # 🔬 Measurement: Observe lower total latency per tick processing in the event loop profiling.
            regime_task = asyncio.create_task(
                self.regime_detector.detect_regime(lazy_df)
            )
            df_task = asyncio.create_task(asyncio.to_thread(lazy_df.collect))
            regime, df = await asyncio.gather(regime_task, df_task)

            # Check Circuit Breaker
            is_crashing = await self._check_circuit_breaker(df)
            if is_crashing:
                # Force a halt signal if circuit breaker trips
                import time

                signal = AISignal(
                    timestamp=int(time.time() * 1000),
                    asset_pair=df["symbol"][0] if df.height > 0 else "UNKNOWN",
                    action="HOLD",
                    confidence_score=1.0,
                    reasoning="CIRCUIT BREAKER: Extreme negative liquidity velocity.",
                )
                if self.on_signal_callback:
                    asyncio.create_task(self.on_signal_callback(signal, regime))
                return

            # PERFORMANCE OPTIMIZATION: Concurrently run AI analysis and modular strategy evaluation
            # 💡 What: Used asyncio.gather to evaluate the deterministic strategy and the LLM/AI engine concurrently.
            # 🎯 Why: Both AI analysis and strategy data processing are independent. Running them sequentially doubles the latency.
            # 📊 Impact: Significantly speeds up signal generation time during market ticks.
            async def evaluate_strategy(ldf):
                if not self.strategy:
                    return "HOLD"
                ldf = self.strategy.populate_indicators(ldf)
                ldf = self.strategy.populate_signals(ldf)
                strat_df = await asyncio.to_thread(ldf.collect)
                if strat_df.height > 0:
                    last_row = strat_df[-1]
                    if "buy" in strat_df.columns and last_row["buy"][0]:
                        return "BUY"
                    elif "sell" in strat_df.columns and last_row["sell"][0]:
                        return "SELL"
                return "HOLD"

            strategy_task = asyncio.create_task(evaluate_strategy(lazy_df))
            ai_task = asyncio.create_task(
                self.ai_engine.analyze_market_state(df, regime=regime)
            )

            strategy_signal, signal = await asyncio.gather(strategy_task, ai_task)

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
