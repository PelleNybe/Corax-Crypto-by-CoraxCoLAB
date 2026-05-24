import polars as pl
import asyncio
from loguru import logger
from typing import Dict, Any, Tuple
from core.strategy import BaseStrategy
from execution.exchange_manager import exchange_manager
from core.config import settings


class CoraxMarketMaker(BaseStrategy):
    """
    High-Frequency Market Making Strategy.
    Calculates optimal quotes and inventory skews to provide liquidity
    while managing directional risk.
    """

    def __init__(
        self,
        name: str = "CoraxMarketMaker",
        params: Dict[str, Any] = None,
        order_manager=None,
        symbols=["BTC/USDT"],
    ):
        super().__init__(name)
        self.params = params or {}
        # Default MM Parameters
        self.params.setdefault("base_spread_bps", 10.0)  # 0.1% base spread
        self.params.setdefault("target_inventory_pct", 0.5)  # 50% base, 50% quote
        self.params.setdefault("max_inventory_skew", 0.2)  # Max deviation from target
        self.params.setdefault("volatility_multiplier", 2.0)

        self.order_manager = order_manager
        self.symbols = symbols
        self.orderbook_queue = exchange_manager.subscribe_orderbook()
        self._worker_task = None

        # State tracking
        self.current_inventory_pct = 0.5
        self.current_regime = "RANGING"

    async def start(self):
        """Starts the background worker to process incoming orderbook updates."""
        logger.info(
            "Starting Corax Market Maker listening to unified orderbook stream..."
        )
        self._worker_task = asyncio.create_task(self._process_orderbooks())

    async def _process_orderbooks(self):
        try:
            while True:
                ob_event = await self.orderbook_queue.get()
                exchange_id = ob_event["exchange_id"]
                symbol = ob_event["symbol"]

                # Only act on primary exchange orderbooks
                if exchange_id != settings.EXCHANGE_ID or symbol not in self.symbols:
                    continue

                orderbook = ob_event["data"]

                if (
                    orderbook
                    and len(orderbook.get("bids", [])) > 0
                    and len(orderbook.get("asks", [])) > 0
                ):
                    best_bid = orderbook["bids"][0][0]
                    best_ask = orderbook["asks"][0][0]
                    mid_price = (best_bid + best_ask) / 2.0

                    bid_price, ask_price = self.calculate_quotes(
                        mid_price, self.current_inventory_pct, self.current_regime
                    )

                    if self.order_manager:
                        # Assuming a fixed trade size for market making here
                        await self.order_manager.requote_market_maker(
                            symbol, bid_price, ask_price, amount=0.01
                        )

        except asyncio.CancelledError:
            logger.info("Market Maker worker cancelled.")
        except Exception as e:
            logger.error(f"Error in Market Maker _process_orderbooks: {e}")

    def calculate_quotes(
        self, current_price: float, current_inventory_pct: float, regime: str
    ) -> Tuple[float, float]:
        """
        Calculates optimal Bid and Ask prices based on volatility and inventory.
        """
        base_spread = self.params["base_spread_bps"] / 10000.0

        # Volatility adjustment
        if regime in ["VOLATILE_CRASH", "VOLATILE_BREAKOUT"]:
            spread = base_spread * self.params["volatility_multiplier"]
        elif regime == "RANGING":
            spread = base_spread * 0.8  # Tighter spread in quiet markets
        else:
            spread = base_spread

        half_spread = spread / 2.0

        # Inventory Skew Logic
        # If holding too much base asset (e.g. > 50%), lower the ask to sell, lower the bid to avoid buying
        skew = current_inventory_pct - self.params["target_inventory_pct"]

        # Limit the skew effect
        skew = max(
            min(skew, self.params["max_inventory_skew"]),
            -self.params["max_inventory_skew"],
        )

        # Shift the mid-price based on skew
        skew_shift = skew * spread
        adjusted_mid = current_price - (current_price * skew_shift)

        bid_price = adjusted_mid * (1 - half_spread)
        ask_price = adjusted_mid * (1 + half_spread)

        return bid_price, ask_price

    def populate_indicators(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """Required by base class, but MM logic is driven by `calculate_quotes` per tick."""
        return df.with_columns(pl.lit(False).alias("entry_signal"))

    def populate_signals(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """Required by base class."""
        return df.with_columns(pl.lit(False).alias("exit_signal"))

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
        await exchange_manager.unsubscribe_orderbook(self.orderbook_queue)
