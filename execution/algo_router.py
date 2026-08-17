import asyncio
from abc import ABC, abstractmethod
from typing import Any, Callable, Coroutine
from loguru import logger


class BaseExecutionAlgo(ABC):
    """Abstract base class for execution algorithms."""

    @abstractmethod
    async def execute(
        self,
        symbol: str,
        side: str,
        amount: float,
        current_price: float,
        place_order_callback: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        """Executes the order using the specific algorithm."""
        raise NotImplementedError


class TWAPManager(BaseExecutionAlgo):
    """Time-Weighted Average Price execution."""

    def __init__(self, duration_mins: int = 10, chunks: int = 5):
        self.duration_mins = duration_mins
        self.chunks = chunks

    async def execute(
        self,
        symbol: str,
        side: str,
        amount: float,
        current_price: float,
        place_order_callback: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        chunk_size = amount / self.chunks
        delay_seconds = (self.duration_mins * 60) / self.chunks

        logger.info(
            f"TWAP {side} {amount} {symbol} over {self.duration_mins}m in {self.chunks} chunks ({chunk_size} per chunk)"
        )

        for i in range(self.chunks):
            logger.debug(
                f"TWAP [{i + 1}/{self.chunks}] placing order for {chunk_size} {symbol}"
            )
            # Ensure the place_order_callback handles 'market' or 'limit' as needed
            await place_order_callback(
                symbol=symbol, side=side, amount=chunk_size, order_type="market"
            )

            if i < self.chunks - 1:
                logger.debug(f"TWAP waiting {delay_seconds}s for next chunk...")
                await asyncio.sleep(delay_seconds)

        logger.success(f"TWAP execution completed for {symbol}.")


class VWAPManager(BaseExecutionAlgo):
    """Volume-Weighted Average Price execution."""

    def __init__(self, duration_mins: int = 10, chunks: int = 5):
        self.duration_mins = duration_mins
        self.chunks = chunks

    async def execute(
        self,
        symbol: str,
        side: str,
        amount: float,
        current_price: float,
        place_order_callback: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        # Simplistic VWAP simulation: wait based on chunk schedules and release sizes.
        # In a full implementation, we'd pull historical volume profiles from CCXT.
        logger.info(
            f"VWAP {side} {amount} {symbol} over {self.duration_mins}m in {self.chunks} chunks"
        )

        delay_seconds = (self.duration_mins * 60) / self.chunks

        # Simulating a volume curve (e.g., U-shape smile for market open/close)
        volume_curve = [1.5, 0.8, 0.7, 0.8, 1.2]

        # If chunks > 5, just flat weight
        if self.chunks != 5:
            volume_curve = [1.0] * self.chunks

        total_weight = sum(volume_curve)

        for i in range(self.chunks):
            weight = volume_curve[i] / total_weight
            chunk_size = amount * weight

            logger.debug(
                f"VWAP [{i + 1}/{self.chunks}] placing order for {chunk_size:.4f} {symbol} (Weight: {weight:.2f})"
            )
            await place_order_callback(
                symbol=symbol, side=side, amount=chunk_size, order_type="market"
            )

            if i < self.chunks - 1:
                logger.debug(f"VWAP waiting {delay_seconds}s for next chunk...")
                await asyncio.sleep(delay_seconds)

        logger.success(f"VWAP execution completed for {symbol}.")


class IcebergManager(BaseExecutionAlgo):
    """Iceberg order execution."""

    def __init__(self, display_fraction: float = 0.1, wait_timeout_sec: int = 300):
        self.display_fraction = display_fraction
        self.wait_timeout_sec = wait_timeout_sec

    async def execute(
        self,
        symbol: str,
        side: str,
        amount: float,
        current_price: float,
        place_order_callback: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        from execution.exchange_manager import exchange_manager
        from core.config import settings

        chunk_size = amount * self.display_fraction
        remaining_amount = amount
        chunks_placed = 0

        logger.info(
            f"Iceberg {side} {amount} {symbol} showing {self.display_fraction * 100}% per slice ({chunk_size})"
        )

        exchange_id = settings.EXCHANGE_ID
        ex = exchange_manager.exchanges.get(exchange_id)

        while remaining_amount > 0:
            current_chunk = min(chunk_size, remaining_amount)
            chunks_placed += 1
            logger.debug(
                f"Iceberg slice [{chunks_placed}] placing order for {current_chunk} {symbol} at {current_price}"
            )

            try:
                # Place a limit order at the current price
                order = await place_order_callback(
                    symbol=symbol,
                    side=side,
                    amount=current_chunk,
                    order_type="limit",
                    price=current_price,
                )

                # If we have the exchange object, watch orders until filled
                if ex and order and "id" in order:
                    order_id = order["id"]
                    start_time = asyncio.get_event_loop().time()
                    filled = False

                    while (
                        asyncio.get_event_loop().time() - start_time
                    ) < self.wait_timeout_sec:
                        try:
                            # Use CCXT Pro watch_orders
                            orders = await ex.watch_orders(symbol)
                            for o in orders:
                                if o["id"] == order_id and o["status"] in [
                                    "closed",
                                    "filled",
                                    "canceled",
                                ]:
                                    filled = True
                                    break
                            if filled:
                                break
                        except Exception as e:
                            logger.debug(
                                f"watch_orders not supported or failed: {e}. Falling back to fetch_order."
                            )
                            # Fallback if watch_orders fails
                            try:
                                o = await ex.fetch_order(order_id, symbol)
                                if o["status"] in ["closed", "filled", "canceled"]:
                                    filled = True
                                    break
                            except Exception as e:
                                logger.warning(f"fetch_order fallback failed: {e}")
                            await asyncio.sleep(2)
                else:
                    # No order object returned or no exchange connected (e.g. Dry Run)
                    # We will just yield execution for a moment
                    await asyncio.sleep(1.0)

            except Exception as e:
                logger.error(f"Iceberg execution failed on slice {chunks_placed}: {e}")
                break

            remaining_amount -= current_chunk

        logger.success(f"Iceberg execution completed for {symbol}.")
