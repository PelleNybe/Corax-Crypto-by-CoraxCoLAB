import asyncio
import time

from loguru import logger

from core.config import settings
from core.risk_manager import RiskManager
from core.state import global_state
from data_engine.persistence import TickLogger
from data_engine.pipeline import MarketDataStream
from execution.arbitrage_engine import ArbitrageEngine
from execution.exchange_manager import exchange_manager
from execution.order_manager import OrderManager
from intelligence.copilot import CoraxCopilot
from intelligence.corax_ai import CoraxAIEngine
from intelligence.market_maker import CoraxMarketMaker
from intelligence.regime_detector import RegimeDetector
from schemas.signals import AISignal


class CoraxEngine:
    """
    The central orchestrator for Corax Crypto.
    """

    def __init__(self):
        self.risk_manager = RiskManager()

        # New unified order manager that uses the singleton exchange manager
        self.order_manager = OrderManager(self.risk_manager)

        self.ai_engine = CoraxAIEngine()
        self.regime_detector = RegimeDetector(ai_backend=self.ai_engine.fast_backend)
        self.copilot = CoraxCopilot()

        # State variables for Omni-Channel hooks
        self.is_paused = False
        self.trading_mode = "DIRECTIONAL"  # DIRECTIONAL, ARBITRAGE, MARKET_MAKING

        async def handle_signal(signal: AISignal, regime: str):
            if self.is_paused:
                logger.debug("Engine is PAUSED. Ignoring incoming signal.")
                return

            await global_state.update_signal(signal, regime)
            await self.order_manager.execute_signal(signal)
            await global_state.update_balance(self.order_manager.available_balance)

        self.data_stream = MarketDataStream(
            ai_engine=self.ai_engine,
            regime_detector=self.regime_detector,
            buffer_size=10,
            on_signal_callback=handle_signal,
        )

        # Initialize Independent TickLogger
        self.tick_logger = TickLogger()

        # Initialize Arbitrage Engine
        self.arbitrage_engine = ArbitrageEngine()
        self.arbitrage_engine.set_signal_callback(
            self.order_manager.execute_arbitrage_legs
        )

        # Initialize Market Maker
        self.market_maker = CoraxMarketMaker(order_manager=self.order_manager)

    async def _copilot_loop(self):
        import hashlib
        import json

        logger.info("Starting LLM Copilot Background Loop...")
        last_summary_hash = None
        try:
            while True:
                summary = global_state.get_summary()

                # Check for state changes to avoid unnecessary LLM calls
                summary_str = json.dumps(summary, sort_keys=True)
                current_hash = hashlib.md5(summary_str.encode()).hexdigest()

                if current_hash != last_summary_hash:
                    synthesis = await self.copilot.generate_synthesis(summary)
                    await global_state.update_synthesis(synthesis)
                    last_summary_hash = current_hash

                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in Copilot loop: {e}")

    async def _simulate_feed(self):
        logger.info("Simulating incoming websocket ticks...")
        symbols = ["BTC/USDT", "ETH/USDT"]
        await global_state.update_balance(self.order_manager.available_balance)

        try:
            for i in range(100):
                if i > 50:
                    price_fluctuation = -500
                else:
                    price_fluctuation = (i % 10) * (1 if i % 2 == 0 else -1)

                mock_tick = {
                    "symbol": symbols[i % 2],
                    "timestamp": int(time.time() * 1000),
                    "price": 50000.0 + i + price_fluctuation,
                    "volume": 0.5 + (i * 0.1),
                    "side": "buy" if i % 2 == 0 else "sell",
                }

                if i > 50 and i % 5 == 0:
                    self.order_manager.available_balance -= 200
                    await global_state.update_balance(
                        self.order_manager.available_balance
                    )

                await global_state.update_tick(mock_tick)
                await self.data_stream.process_tick(mock_tick)
                await asyncio.sleep(0.5)
            logger.info("Simulated feed finished. Engine will remain active.")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in simulate feed: {e}")

    async def run(self):
        logger.info("Starting Corax Engine...")
        if settings.CORAX_MODE.lower() == "testnet":
            logger.warning("⚠️ RUNNING IN ARC TESTNET MODE - NO REAL CAPITAL AT RISK")

        # Initialize Unified Exchange Manager
        await exchange_manager.initialize()
        exchange_manager.start_monitoring()

        # Start specific strategies/engines
        await self.arbitrage_engine.start()
        await self.market_maker.start()

        from core.api_server import app

        # Inject OrderManager and Engine into FastAPI app state for manual trading via REST API
        app.state.order_manager = self.order_manager
        app.state.engine = self

        # NOTE: Uvicorn is intentionally NOT started here. It is handled by main.py.

        copilot_task = asyncio.create_task(self._copilot_loop())

        # Start telegram bot if token exists
        telegram_task = None
        if settings.TELEGRAM_BOT_TOKEN:
            from ui.telegram_interface import CoraxTelegramInterface

            self.telegram_ui = CoraxTelegramInterface(self)
            telegram_task = asyncio.create_task(self.telegram_ui.start_polling())

        feed_task = asyncio.create_task(self._simulate_feed())

        try:
            # The engine must stay alive indefinitely. We should not shut down
            # just because the simulation finishes.
            while True:
                await asyncio.sleep(3600)

        except asyncio.CancelledError:
            logger.info("Corax Engine received cancellation signal.")
        except Exception as e:
            logger.exception(f"Unexpected fatal error in Corax Engine main loop: {e}")
        finally:
            logger.info("Shutting down Corax Engine...")
            copilot_task.cancel()
            feed_task.cancel()

            await self.tick_logger.shutdown()
            await self.arbitrage_engine.stop()
            await self.market_maker.stop()
            await self.order_manager.shutdown()

            if telegram_task:
                telegram_task.cancel()
                await self.telegram_ui.stop()

            await exchange_manager.close_all()
