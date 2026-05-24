import asyncio
import time
import ccxt.pro as ccxtpro
from loguru import logger
from typing import Dict, Any, List, Optional
from core.config import settings


class RateLimitController:
    """
    Centralized rate-limit controller to guard against IP bans from rapid CANCEL/CREATE loops.
    Ensures that burst requests do not exceed the exchange's permissible rate limits.
    """

    def __init__(self, calls_per_second: float = 10.0):
        self.calls_per_second = calls_per_second
        self.interval = 1.0 / calls_per_second
        self.last_call_time = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            time_since_last_call = now - self.last_call_time
            if time_since_last_call < self.interval:
                sleep_time = self.interval - time_since_last_call
                await asyncio.sleep(sleep_time)
            self.last_call_time = time.monotonic()


class ExchangeManager:
    """
    Singleton Manager for unified ccxt.pro WebSocket connections.
    Maintains persistent connections, handles auto-reconnections, heartbeats,
    and broadcasts market data via a pub/sub pattern using asyncio.Queue.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ExchangeManager, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.exchanges: Dict[str, ccxtpro.Exchange] = {}
        self.rate_limiters: Dict[str, RateLimitController] = {}

        # Pub/Sub queues
        self.orderbook_subscribers: List[asyncio.Queue] = []
        self.trade_subscribers: List[asyncio.Queue] = []

        self._running = False
        self._monitor_tasks: List[asyncio.Task] = []

    async def initialize(self):
        """Initializes all exchange connections based on ARBITRAGE_EXCHANGES config."""
        logger.info(
            f"Initializing Unified Exchange Manager with: {settings.ARBITRAGE_EXCHANGES}"
        )
        for exchange_id in settings.ARBITRAGE_EXCHANGES:
            try:
                exchange_class = getattr(ccxtpro, exchange_id)
                auth_params = {
                    "enableRateLimit": True,
                    "newUpdates": True,  # Required to get only new updates from orderbooks
                }

                # Apply auth for the primary exchange
                if exchange_id == settings.EXCHANGE_ID:
                    auth_params["apiKey"] = settings.EXCHANGE_API_KEY
                    auth_params["secret"] = settings.EXCHANGE_API_SECRET
                    if settings.EXCHANGE_PASSPHRASE:
                        auth_params["password"] = settings.EXCHANGE_PASSPHRASE

                self.exchanges[exchange_id] = exchange_class(auth_params)
                if settings.CORAX_MODE.lower() == "testnet":
                    self.exchanges[exchange_id].set_sandbox_mode(True)
                    logger.info(f"Enabled Sandbox mode for {exchange_id}")

                self.rate_limiters[exchange_id] = RateLimitController(
                    calls_per_second=10.0
                )  # Configure based on exchange later

                await self.exchanges[exchange_id].load_markets()
                logger.info(f"Successfully loaded markets for {exchange_id}")
            except Exception as e:
                logger.error(f"Failed to initialize exchange {exchange_id}: {e}")

        self._running = True

    def subscribe_orderbook(self) -> asyncio.Queue:
        """Returns an asyncio.Queue that receives L2 orderbook updates."""
        queue = asyncio.Queue()
        self.orderbook_subscribers.append(queue)
        return queue

    def subscribe_trades(self) -> asyncio.Queue:
        """Returns an asyncio.Queue that receives live trade ticks."""
        queue = asyncio.Queue()
        self.trade_subscribers.append(queue)
        return queue

    async def unsubscribe_orderbook(self, queue: asyncio.Queue):
        if queue in self.orderbook_subscribers:
            self.orderbook_subscribers.remove(queue)

    async def unsubscribe_trades(self, queue: asyncio.Queue):
        if queue in self.trade_subscribers:
            self.trade_subscribers.remove(queue)

    async def _broadcast_orderbook(self, exchange_id: str, symbol: str, orderbook: Any):
        payload = {"exchange_id": exchange_id, "symbol": symbol, "data": orderbook}
        if self.orderbook_subscribers:
            await asyncio.gather(*(q.put(payload) for q in self.orderbook_subscribers))

    async def _broadcast_trades(self, exchange_id: str, symbol: str, trades: Any):
        payload = {"exchange_id": exchange_id, "symbol": symbol, "data": trades}
        if self.trade_subscribers:
            await asyncio.gather(*(q.put(payload) for q in self.trade_subscribers))

    async def _watch_orderbook_loop(self, exchange_id: str, symbol: str):
        """Continuously streams orderbook data for a specific exchange and symbol."""
        exchange = self.exchanges[exchange_id]
        consecutive_failures = 0
        max_failures = 3

        while self._running:
            try:
                orderbook = await exchange.watch_order_book(symbol)
                consecutive_failures = 0  # Reset on success
                await self._broadcast_orderbook(exchange_id, symbol, orderbook)
            except ccxtpro.NetworkError as e:
                consecutive_failures += 1
                if consecutive_failures > max_failures:
                    logger.info(
                        f"Dropping orderbook stream {exchange_id} for {symbol} after {max_failures} consecutive failures."
                    )
                    break

                log_msg = f"Network error in orderbook stream {exchange_id} for {symbol}: {e}. Reconnecting..."
                if consecutive_failures == 1:
                    logger.warning(log_msg)
                else:
                    logger.debug(log_msg)

                await asyncio.sleep(
                    min(5 * (2 ** (consecutive_failures - 1)), 60)
                )  # Exponential backoff
            except Exception as e:
                consecutive_failures += 1
                if consecutive_failures > max_failures:
                    logger.info(
                        f"Dropping orderbook stream {exchange_id} for {symbol} after {max_failures} consecutive failures."
                    )
                    break

                log_msg = f"Error in orderbook stream {exchange_id} for {symbol}: {e}. Retrying..."
                if consecutive_failures == 1:
                    logger.warning(log_msg)
                else:
                    logger.debug(log_msg)

                await asyncio.sleep(min(5 * (2 ** (consecutive_failures - 1)), 60))

    async def _watch_trades_loop(self, exchange_id: str, symbol: str):
        """Continuously streams live trades for a specific exchange and symbol."""
        exchange = self.exchanges[exchange_id]
        consecutive_failures = 0
        max_failures = 3

        while self._running:
            try:
                trades = await exchange.watch_trades(symbol)
                consecutive_failures = 0  # Reset on success
                await self._broadcast_trades(exchange_id, symbol, trades)
            except ccxtpro.NetworkError as e:
                consecutive_failures += 1
                if consecutive_failures > max_failures:
                    logger.info(
                        f"Dropping trades stream {exchange_id} for {symbol} after {max_failures} consecutive failures."
                    )
                    break

                log_msg = f"Network error in trades stream {exchange_id} for {symbol}: {e}. Reconnecting..."
                if consecutive_failures == 1:
                    logger.warning(log_msg)
                else:
                    logger.debug(log_msg)

                await asyncio.sleep(
                    min(5 * (2 ** (consecutive_failures - 1)), 60)
                )  # Exponential backoff
            except Exception as e:
                consecutive_failures += 1
                if consecutive_failures > max_failures:
                    logger.info(
                        f"Dropping trades stream {exchange_id} for {symbol} after {max_failures} consecutive failures."
                    )
                    break

                log_msg = f"Error in trades stream {exchange_id} for {symbol}: {e}. Retrying..."
                if consecutive_failures == 1:
                    logger.warning(log_msg)
                else:
                    logger.debug(log_msg)

                await asyncio.sleep(min(5 * (2 ** (consecutive_failures - 1)), 60))

    def start_monitoring(self, symbols: List[str] = ["BTC/USDT", "ETH/USDT"]):
        """Starts background tasks to stream data for all configured exchanges and symbols."""
        logger.info(f"Starting unified WebSocket streams for symbols: {symbols}")
        for exchange_id in self.exchanges:
            for symbol in symbols:
                # Start Orderbook streams
                ob_task = asyncio.create_task(
                    self._watch_orderbook_loop(exchange_id, symbol)
                )
                self._monitor_tasks.append(ob_task)

                # Start Trades streams
                tr_task = asyncio.create_task(
                    self._watch_trades_loop(exchange_id, symbol)
                )
                self._monitor_tasks.append(tr_task)

    async def execute_order(
        self,
        exchange_id: str,
        symbol: str,
        type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
    ) -> Any:
        """Executes an order using the centralized rate limiter."""
        if exchange_id not in self.exchanges:
            logger.error(f"Cannot execute order: {exchange_id} not initialized.")
            return None

        limiter = self.rate_limiters.get(exchange_id)
        if limiter:
            await limiter.acquire()

        exchange = self.exchanges[exchange_id]
        try:
            logger.debug(
                f"Creating {side} {type} order for {amount} {symbol} on {exchange_id}"
            )
            order = await exchange.create_order(symbol, type, side, amount, price)
            return order
        except Exception as e:
            logger.error(f"Error creating order on {exchange_id}: {e}")
            return None

    async def cancel_order(self, exchange_id: str, order_id: str, symbol: str) -> bool:
        """Cancels an order using the centralized rate limiter."""
        if exchange_id not in self.exchanges:
            logger.error(f"Cannot cancel order: {exchange_id} not initialized.")
            return False

        limiter = self.rate_limiters.get(exchange_id)
        if limiter:
            await limiter.acquire()

        exchange = self.exchanges[exchange_id]
        try:
            logger.debug(f"Cancelling order {order_id} on {exchange_id}")
            await exchange.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            logger.error(f"Error cancelling order {order_id} on {exchange_id}: {e}")
            return False

    async def close_all(self):
        """Gracefully closes all connections and stops monitoring tasks."""
        self._running = False
        logger.info("Closing Unified Exchange Manager connections...")

        for task in self._monitor_tasks:
            task.cancel()

        close_tasks = []
        for name, exchange in self.exchanges.items():
            close_tasks.append(exchange.close())

        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        logger.info("All exchange connections closed.")


exchange_manager = ExchangeManager()
