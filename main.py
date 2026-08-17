import asyncio
import os
import sys

import uvicorn
from loguru import logger
from contextlib import asynccontextmanager

from core.api_server import app
from core.config import settings
from core.engine import CoraxEngine

# Configure Loguru
os.makedirs("logs", exist_ok=True)
logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)
logger.add(
    "logs/corax_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="7 days",
    level="DEBUG",
)

logger.add(
    "logs/corax_errors_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="7 days",
    level="ERROR",
    backtrace=True,
    diagnose=True,
)


def custom_exception_handler(loop, context):
    msg = context.get("exception", context["message"])
    logger.error(f"Caught async exception: {msg}")


@asynccontextmanager
async def lifespan(app):
    # Initialize Engine
    engine = CoraxEngine()

    # 1. Start the trading engine as a background task during app lifespan
    logger.info("Starting Corax Engine background task...")
    engine_task = asyncio.create_task(engine.run())

    yield

    # 2. Clean shutdown when FastAPI shuts down
    logger.info("Shutting down processes gracefully...")
    engine_task.cancel()
    try:
        await engine_task
    except asyncio.CancelledError:
        logger.info("Corax Engine task was cancelled during shutdown.")


# Attach the lifespan to the FastAPI app
app.router.lifespan_context = lifespan


async def main():
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(custom_exception_handler)

    logger.info("=" * 50)
    logger.info(f"BOOTSTRAPPING CORAX CRYPTO - ENV: {settings.CORAX_ENV}")
    logger.info("=" * 50)

    # 3. Start the Uvicorn web server as the main blocking process
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    try:
        await server.serve()
    except asyncio.CancelledError:
        logger.info("Uvicorn server was cancelled during shutdown.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received Keyboard Interrupt. Exiting...")
    except Exception as e:
        print(f"Failed to start Corax Crypto: {e}")
