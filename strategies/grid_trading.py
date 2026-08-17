import polars as pl
from loguru import logger
from core.strategy import BaseStrategy
from core.config import settings


class GridTrading(BaseStrategy):
    """
    Native Grid Trading Strategy (Pionex/Bitsgap style).
    Calculates arithmetic grid levels and populates limit orders via the engine.
    """

    def __init__(self, name="GridTrading"):
        super().__init__(name)
        self.upper_price = settings.GRID_UPPER_PRICE
        self.lower_price = settings.GRID_LOWER_PRICE
        self.levels = settings.GRID_LEVELS

        # Avoid zero division
        if self.levels < 2:
            self.levels = 2

    def populate_indicators(self, df: pl.LazyFrame) -> pl.LazyFrame:
        # Grid trading does not rely on traditional indicators like RSI/MACD,
        # it purely maps mathematical bounds.
        return df

    def populate_signals(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """
        Grid bots don't generate single directional signals like trend-followers.
        Instead, they initialize the grid and let the execution engine handle Limit orders.
        We will return 'HOLD' for all rows, but we will attach a custom hook for the engine.
        """
        df = df.with_columns(pl.lit(False).alias("buy"), pl.lit(False).alias("sell"))
        return df

    def generate_grid(
        self, current_price: float, total_investment: float
    ) -> list[dict]:
        """
        Calculates the grid levels dynamically based on current price.
        Returns a list of dicts representing the buy/sell limit orders.
        """
        if current_price > self.upper_price or current_price < self.lower_price:
            logger.warning(
                f"Current price {current_price} is out of grid bounds ({self.lower_price} - {self.upper_price})."
            )
            return []

        step = (self.upper_price - self.lower_price) / (self.levels - 1)
        amount_per_line = (
            total_investment / self.levels
        ) / current_price  # Approximation

        grid_lines = []

        for i in range(self.levels):
            price_level = self.lower_price + (step * i)

            # If price level is below current price, it's a BUY limit waiting to catch dips
            # If price level is above current price, it's a SELL limit waiting to catch rips
            if price_level < current_price:
                side = "buy"
            else:
                side = "sell"

            grid_lines.append(
                {"price": price_level, "side": side, "amount": amount_per_line}
            )

        logger.info(
            f"Generated Arithmetic Grid with {self.levels} levels between {self.lower_price} and {self.upper_price}. Step: {step:.2f}"
        )
        return grid_lines
