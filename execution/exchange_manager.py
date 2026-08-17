import asyncio
import time
import ccxt.pro as ccxtpro
from loguru import logger
from typing import Dict, Any, List
from schemas.orders import OrderContext
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
        """Initializes all exchange connections based on config."""
        import json

        # Load Main Account
        exchanges_to_load = {
            settings.EXCHANGE_ID or "": {
                "exchange": settings.EXCHANGE_ID or "",
                "apiKey": settings.EXCHANGE_API_KEY,
                "secret": settings.EXCHANGE_API_SECRET,
                "password": settings.EXCHANGE_PASSPHRASE,
            }
        }

        # Load Arbitrage Accounts (Read-only usually, but mapped)
        for ex in settings.ARBITRAGE_EXCHANGES:
            if ex not in exchanges_to_load:
                exchanges_to_load[ex] = {"exchange": ex}

        # Load Multi-Accounts (Copy Trading)
        if settings.COPY_TRADE_ENABLED:
            try:
                multi_cfg = json.loads(settings.MULTI_ACCOUNT_CONFIG)
                for account_id, creds in multi_cfg.items():
                    if "exchange" in creds:
                        # Append account_id to make it unique in self.exchanges map
                        exchanges_to_load[f"{creds['exchange']}_{account_id}"] = creds
            except Exception as e:
                logger.error(f"Failed to parse MULTI_ACCOUNT_CONFIG: {e}")

        logger.info(
            f"Initializing Unified Exchange Manager with accounts: {list(exchanges_to_load.keys())}"
        )

        for account_key, creds in exchanges_to_load.items():
            exchange_id = creds["exchange"]

            # Special handling for Web3 native DEXs (Not in CCXT by default)
            if exchange_id in ["uniswap", "pancakeswap", "curve"]:
                logger.info(
                    f"Skipping CCXT load for native DEX: {exchange_id}. Managed via Web3Bridge."
                )
                continue

            try:
                if not hasattr(ccxtpro, exchange_id):
                    logger.warning(
                        f"Exchange {exchange_id} is not supported by ccxt.pro."
                    )
                    continue

                exchange_class = getattr(ccxtpro, exchange_id)
                auth_params = {
                    "enableRateLimit": True,
                    "newUpdates": True,  # Required to get only new updates from orderbooks
                    "options": {
                        "defaultType": settings.MARKET_TYPE,  # e.g. "spot", "future", "swap"
                    },
                }

                if "apiKey" in creds:
                    auth_params["apiKey"] = creds["apiKey"]
                    auth_params["secret"] = creds["secret"]
                    if creds.get("password"):
                        auth_params["password"] = creds["password"]

                self.exchanges[account_key] = exchange_class(auth_params)

                # Setup institutional leverage if applicable
                if settings.MARKET_TYPE in ["future", "swap", "margin"]:
                    try:
                        # Wait for markets to load before setting leverage
                        # Note: We do this asynchronously in a background task to not block init
                        async def set_leverage(acc_key, ex):
                            await ex.load_markets()
                            for symbol in ex.markets.keys():
                                try:
                                    if symbol.endswith("/USDT:USDT") or symbol.endswith(
                                        "/USDT"
                                    ):
                                        await ex.set_leverage(settings.LEVERAGE, symbol)
                                except Exception:
                                    pass  # Many exchanges only allow setting leverage per-symbol, some globally.
                            logger.info(
                                f"[{acc_key}] Leverage set to {settings.LEVERAGE}x"
                            )

                        if hasattr(self.exchanges[account_key], "set_leverage"):
                            asyncio.create_task(
                                set_leverage(account_key, self.exchanges[account_key])
                            )
                    except Exception as e:
                        logger.warning(f"Could not set leverage on {account_key}: {e}")

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
            for q in self.orderbook_subscribers:
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    logger.warning(
                        f"Orderbook queue full for {exchange_id} {symbol}, dropping update"
                    )

    async def _broadcast_trades(self, exchange_id: str, symbol: str, trades: Any):
        payload = {"exchange_id": exchange_id, "symbol": symbol, "data": trades}
        if self.trade_subscribers:
            for q in self.trade_subscribers:
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    logger.warning(
                        f"Trades queue full for {exchange_id} {symbol}, dropping update"
                    )

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
        context: OrderContext,
        params: dict = None,
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
                f"Creating {context.side} {context.order_type} order for {context.amount} {context.symbol} on {exchange_id}"
            )

            if params is None:
                params = {}
            order = await exchange.create_order(
                context.symbol,
                context.order_type,
                context.side,
                context.amount,
                context.current_price,
                params,
            )

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


class AccountManager:
    """Manages multiple CCXT exchange instances for different sub-accounts."""

    def __init__(self):
        self.accounts: Dict[str, Any] = {}

    async def add_account(
        self, account_id: str, exchange_id: str, api_key: str, api_secret: str
    ):
        if not hasattr(ccxtpro, exchange_id):
            raise ValueError(f"Exchange {exchange_id} not supported by ccxt.pro")

        exchange_class = getattr(ccxtpro, exchange_id)
        self.accounts[account_id] = exchange_class(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": getattr(settings, "MARKET_TYPE", "spot")},
            }
        )

    async def get_all_accounts(self) -> Dict[str, Any]:
        return self.accounts


account_manager = AccountManager()
