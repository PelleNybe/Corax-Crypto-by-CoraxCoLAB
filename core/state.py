import asyncio
from loguru import logger
from typing import List, Dict, Any
from schemas.signals import AISignal
from core.config import settings


class GlobalState:
    """
    Thread-safe global state for the trading engine.
    Stores latest signals, positions, and manages active websocket connections
    for broadcasting to UI dashboards.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self.latest_signal: AISignal | None = None
        self.recent_ticks: List[Dict[str, Any]] = []
        self.max_ticks = 100
        self.active_connections: List[asyncio.Queue] = []
        self.current_balance = 10000.0
        self.current_regime = "UNKNOWN"
        self.latest_synthesis = "Initializing LLM Copilot..."
        self.run_mode = "DRY_RUN" if settings.DRY_RUN_MODE else "LIVE"
        self._current_kline = None

    async def add_connection(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        async with self._lock:
            self.active_connections.append(queue)
        logger.info(
            f"New client connected. Total connections: {len(self.active_connections)}"
        )
        return queue

    async def remove_connection(self, queue: asyncio.Queue):
        async with self._lock:
            if queue in self.active_connections:
                self.active_connections.remove(queue)
        logger.info(
            f"Client disconnected. Total connections: {len(self.active_connections)}"
        )

    async def _broadcast(self, data: Dict[str, Any]):
        async with self._lock:
            tasks = []
            for queue in self.active_connections:
                tasks.append(queue.put(data))
            if tasks:
                await asyncio.gather(*tasks)

    async def update_tick(self, tick: Dict[str, Any]):
        async with self._lock:
            self.recent_ticks.append(tick)
            if len(self.recent_ticks) > self.max_ticks:
                self.recent_ticks.pop(0)

            # Aggregate into OHLCV for Lightweight Charts (e.g., 1-second candles for visual speed)
            price = tick.get("price", 0.0)
            vol = tick.get("volume", 0.0)
            ts = tick.get("timestamp", 0)
            # Group by 1-minute intervals (60000 ms), but use seconds for timestamp per TradingView specs
            # Lightweight charts expects unix timestamp in seconds for default time.
            candle_time = (ts // 60000) * 60

            if not self._current_kline or self._current_kline["time"] != candle_time:
                # New candle
                self._current_kline = {
                    "time": candle_time,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": vol,
                }
            else:
                # Update existing
                self._current_kline["high"] = max(self._current_kline["high"], price)
                self._current_kline["low"] = min(self._current_kline["low"], price)
                self._current_kline["close"] = price
                self._current_kline["volume"] += vol

            # We need to broadcast the kline copy to avoid race conditions
            kline_copy = dict(self._current_kline)

        await self._broadcast({"type": "tick", "data": tick})
        await self._broadcast({"action": "kline", "data": kline_copy})

    async def update_signal(self, signal: AISignal, regime: str):
        async with self._lock:
            self.latest_signal = signal
            self.current_regime = regime
        await self._broadcast(
            {"type": "signal", "data": signal.model_dump(), "regime": regime}
        )

    async def update_balance(self, balance: float):
        async with self._lock:
            self.current_balance = balance
        await self._broadcast(
            {"type": "balance", "data": {"balance": balance, "mode": self.run_mode}}
        )

    async def update_synthesis(self, synthesis: str):
        async with self._lock:
            self.latest_synthesis = synthesis
        await self._broadcast({"type": "synthesis", "data": {"text": synthesis}})

    @property
    def synthesis(self) -> str:
        return self.latest_synthesis

    def get_summary(self) -> Dict[str, Any]:
        """Provides a snapshot for the LLM Copilot."""
        action = self.latest_signal.action if self.latest_signal else "HOLD"
        last_price = (
            self.recent_ticks[-1].get("price", 50000.0)
            if self.recent_ticks
            else 50000.0
        )
        return {
            "regime": self.current_regime,
            "balance": self.current_balance,
            "recent_action": action,
            "mode": self.run_mode,
            "last_price": last_price,
        }


global_state = GlobalState()
