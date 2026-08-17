import asyncio
from loguru import logger
from typing import Dict, Any, Coroutine, Callable
from schemas.orders import GridState, GridLine


class GridManager:
    """
    Manages continuous Grid Trading limit orders.
    Places a series of buy and sell limit orders around the current price.
    """

    def __init__(
        self,
        place_order_callback: Callable[..., Coroutine[Any, Any, Any]],
        cancel_order_callback: Callable[..., Coroutine[Any, Any, Any]],
    ):
        self.place_order_callback = place_order_callback
        self.cancel_order_callback = cancel_order_callback
        self.grids: Dict[str, GridState] = {}

    async def initialize_grid(
        self,
        symbol: str,
        current_price: float,
        lower_price: float,
        upper_price: float,
        grid_levels: int,
        total_amount: float,
    ):
        """Initializes a new grid for a symbol."""
        logger.info(
            f"Initializing Grid for {symbol} from {lower_price} to {upper_price} with {grid_levels} levels."
        )
        price_step = (upper_price - lower_price) / grid_levels
        amount_per_level = total_amount / grid_levels

        lines = []
        for i in range(grid_levels + 1):
            level_price = lower_price + (i * price_step)
            side = "buy" if level_price < current_price else "sell"

            # Avoid placing orders exactly at current price to prevent instant fills
            if abs(level_price - current_price) / current_price < 0.001:
                continue

            lines.append(
                GridLine(price=level_price, side=side, amount=amount_per_level)
            )

        state = GridState(symbol=symbol, lines=lines)
        self.grids[symbol] = state

        await self._deploy_grid(state)

    async def _deploy_grid(self, state: GridState):
        """Deploys the orders in the grid state."""
        tasks = []
        for line in state.lines:
            if not line.is_active:
                tasks.append(self._place_grid_line(state.symbol, line))

        if tasks:
            await asyncio.gather(*tasks)

    async def _place_grid_line(self, symbol: str, line: GridLine):
        try:
            order_res = await self.place_order_callback(
                symbol=symbol,
                side=line.side,
                amount=line.amount,
                order_type="limit",
                price=line.price,
            )
            line.order_id = order_res.get("id", "mock_id")
            line.is_active = True
            logger.debug(
                f"Grid placed {line.side} at {line.price} for {symbol} (ID: {line.order_id})"
            )
        except Exception as e:
            logger.error(f"Failed to place grid order for {symbol}: {e}")

    async def on_order_filled(self, symbol: str, order_id: str):
        """Called when a websocket update indicates a grid order was filled."""
        if symbol not in self.grids:
            return

        state = self.grids[symbol]
        filled_line = next(
            (line for line in state.lines if line.order_id == order_id), None
        )

        if filled_line:
            logger.info(
                f"Grid order filled: {filled_line.side} at {filled_line.price} for {symbol}."
            )
            filled_line.is_active = False
            filled_line.order_id = None

            # Switch side and deploy slightly adjusted replacement order
            new_side = "sell" if filled_line.side == "buy" else "buy"
            price_step = 0.01 * filled_line.price  # Dummy logic for step size
            new_price = (
                filled_line.price + price_step
                if new_side == "sell"
                else filled_line.price - price_step
            )

            filled_line.side = new_side
            filled_line.price = new_price

            logger.info(f"Grid replacing order: {new_side} at {new_price}")
            await self._place_grid_line(symbol, filled_line)
