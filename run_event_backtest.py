import asyncio
import os
import sys
import time
from loguru import logger
from core.backtester_event import EventDrivenBacktester
from schemas.signals import AISignal

# Configure Loguru for CLI
logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>",
)


async def dummy_strategy(row: dict) -> AISignal:
    """A simple dummy strategy for testing the event loop."""
    import random

    ts = int(time.time() * 1000)
    symbol = row.get("symbol", "BTC/USDT")

    if random.random() > 0.90:
        action = random.choice(["BUY", "SELL"])
        return AISignal(
            timestamp=ts,
            action=action,
            asset_pair=symbol,
            confidence_score=0.8,
            reasoning="Random test signal for volatility breakout.",
        )
    return AISignal(
        timestamp=ts,
        action="HOLD",
        asset_pair=symbol,
        confidence_score=0.1,
        reasoning="Market is ranging.",
    )


async def main():
    logger.info("=" * 50)
    logger.info("CORAX EVENT-DRIVEN TICK BACKTESTER")
    logger.info("=" * 50)

    parquet_path = "data/market_ticks.parquet"
    if not os.path.exists(parquet_path):
        import polars as pl

        os.makedirs("data", exist_ok=True)
        df = pl.DataFrame(
            {
                "timestamp": [1670000000000 + i * 1000 for i in range(100)],
                "symbol": ["BTC/USDT"] * 100,
                "bid": [20000 + i for i in range(100)],
                "ask": [20001 + i for i in range(100)],
                "close": [20000.5 + i for i in range(100)],
                "volume": [1.5] * 100,
            }
        )
        df.write_parquet(parquet_path)
        logger.info(f"Created sample mock data at {parquet_path}")

    backtester = EventDrivenBacktester(
        parquet_path=parquet_path, latency_ms=10
    )  # Reduced for test speed
    await backtester.run(strategy_callback=dummy_strategy)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Backtest aborted by user.")
