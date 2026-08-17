import asyncio

from loguru import logger

from core.config import settings
from core.risk_manager import RiskManager
from core.state import global_state
from core.event_bus import event_bus
from core.vault_manager import vault_manager
from data_engine.persistence import TickLogger
from data_engine.pipeline import MarketDataStream
from execution.arbitrage_engine import ArbitrageEngine
from execution.exchange_manager import exchange_manager, account_manager
from execution.order_manager import OrderManager
from intelligence.copilot import CoraxCopilot
from intelligence.corax_ai import CoraxAIEngine
from intelligence.market_maker import CoraxMarketMaker
from intelligence.regime_detector import RegimeDetector
from schemas.signals import AISignal
from strategies.grid_trading import GridTrading


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

        self.is_paused = False
        self.trading_mode = "DIRECTIONAL"  # DIRECTIONAL, ARBITRAGE, MARKET_MAKING, GRID

        # Initialize Grid Trading if configured
        if settings.CORAX_MODE.lower() == "grid":
            self.trading_mode = "GRID"
            self.grid_strategy = GridTrading()
            # We defer actual deployment to a background task once live feed gets the first price

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
                # Security: Use SHA-256 instead of MD5 to prevent collision attacks
                current_hash = hashlib.sha256(summary_str.encode()).hexdigest()

                if current_hash != last_summary_hash:
                    synthesis = await self.copilot.generate_synthesis(summary)
                    await global_state.update_synthesis(synthesis)
                    last_summary_hash = current_hash

                await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("Copilot loop cancelled.")
        except Exception as e:
            logger.error(f"Error in Copilot loop: {e}")

    async def _live_data_feed(self):
        """
        Subscribes to live websocket streams via CCXT for active pairs.
        Replaces the old _simulate_feed.
        """
        logger.info("Connecting to live market data feeds...")
        await global_state.update_balance(self.order_manager.available_balance)

        try:
            # We fetch a primary exchange to stream from, e.g., Binance
            exchange = None
            if exchange_manager.active_exchanges:
                exchange = list(exchange_manager.active_exchanges.values())[0]

            if not exchange or not exchange.has.get("watchTrades"):
                logger.warning(
                    "No exchange supports watchTrades. Polling fallback not implemented."
                )
                return

            # Example: Predefined pairs for demonstration.
            # In full production, this comes from pair_manager.py

            # Example: Predefined pairs for demonstration.
            # In full production, this comes from pair_manager.py
            symbols = ["BTC/USDT", "ETH/USDT"]

            # Auto-deploy Grid if in GRID mode
            if self.trading_mode == "GRID":
                try:
                    for symbol in symbols:
                        ticker = await exchange.fetch_ticker(symbol)
                        current_price = ticker["last"]
                        total_investment = (
                            self.order_manager.available_balance
                            * self.risk_manager.max_risk_per_trade
                        )
                        lines = self.grid_strategy.generate_grid(
                            current_price, total_investment
                        )
                        if lines:
                            await self.order_manager.initialize_grid(
                                symbol, current_price, total_investment, lines
                            )
                except Exception as e:
                    logger.error(f"Failed to auto-deploy grid: {e}")

            async def fetch_and_process(sym):
                while True:
                    try:
                        # ccxt.pro watchTrades returns a list of trades
                        trades = await exchange.watch_trades(sym)

                        # PERFORMANCE OPTIMIZATION: Async Batching
                        # 💡 What: Use asyncio.gather for tick processing and state updates.
                        # 🎯 Why: Previously, each trade inside the trades list was processed sequentially,
                        # awaiting each step before moving to the next trade. By using asyncio.gather, we can
                        # process all trades in the current batch concurrently, drastically reducing overall latency.

                        process_tasks = []
                        for trade in trades:
                            live_tick = {
                                "symbol": sym,
                                "timestamp": trade["timestamp"],
                                "price": float(trade["price"]),
                                "volume": float(trade["amount"]),
                                "side": trade["side"],
                            }

                            async def process_single_tick(tick):
                                await global_state.update_tick(tick)
                                await self.data_stream.process_tick(tick)
                                await event_bus.publish("topic:market_data", tick)

                                # World-Class Feature 2: Smart Trade & Trailing Take Profit (TTP) Check
                                sym_ = tick["symbol"]
                                price = tick["price"]

                                # Check TSL
                                if await self.risk_manager.check_trailing_stops(
                                    sym_, price
                                ):
                                    logger.warning(
                                        f"TSL hit for {sym_}. Emitting SELL signal."
                                    )
                                    await self.order_manager.execute_signal(
                                        AISignal(
                                            timestamp=tick["timestamp"],
                                            asset_pair=sym_,
                                            action="SELL",
                                            confidence_score=1.0,
                                            reasoning="Trailing Stop Loss Triggered",
                                        ),
                                        global_state.current_regime,
                                    )
                                    await self.risk_manager.clear_position(sym_)

                                # Check TTP
                                elif await self.risk_manager.check_trailing_take_profit(
                                    sym_, price
                                ):
                                    logger.success(
                                        f"TTP hit for {sym_}. Emitting SELL signal."
                                    )
                                    await self.order_manager.execute_signal(
                                        AISignal(
                                            timestamp=tick["timestamp"],
                                            asset_pair=sym_,
                                            action="SELL",
                                            confidence_score=1.0,
                                            reasoning="Trailing Take Profit Triggered",
                                        ),
                                        global_state.current_regime,
                                    )
                                    await self.risk_manager.clear_position(sym_)

                            process_tasks.append(process_single_tick(live_tick))

                        if process_tasks:
                            await asyncio.gather(*process_tasks)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.debug(f"Watch trades yield error for {sym}: {e}")
                        await asyncio.sleep(1)  # Backoff on error

            tasks = [asyncio.create_task(fetch_and_process(sym)) for sym in symbols]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            logger.info("Live data feed cancelled.")
        except Exception as e:
            logger.error(f"Error in live feed: {e}")

    async def run(self):
        logger.info("Starting Corax Engine...")
        if settings.CORAX_MODE.lower() == "testnet":
            logger.warning("⚠️ RUNNING IN ARC TESTNET MODE - NO REAL CAPITAL AT RISK")

        # Enterprise Security: Load secrets dynamically from Vault
        api_key = await vault_manager.get_secret("exchange/keys", "EXCHANGE_API_KEY")
        api_secret = await vault_manager.get_secret(
            "exchange/keys", "EXCHANGE_API_SECRET"
        )
        if api_key:
            settings.EXCHANGE_API_KEY = api_key
        if api_secret:
            settings.EXCHANGE_API_SECRET = api_secret

        # Multi-Account / Execution Router Initialization
        # In a real environment, these would be loaded from a DB or Vault loop
        await account_manager.add_account(
            account_id="primary_sub",
            exchange_id=settings.EXCHANGE_ID,
            api_key=settings.EXCHANGE_API_KEY,
            api_secret=settings.EXCHANGE_API_SECRET,
        )

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

        feed_task = asyncio.create_task(self._live_data_feed())

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
