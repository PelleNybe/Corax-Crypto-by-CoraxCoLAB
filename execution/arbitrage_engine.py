import asyncio
import itertools
import time
from loguru import logger
from core.config import settings
from execution.exchange_manager import exchange_manager
from execution.profit_calculator import ProfitCalculator, ProfitabilityRequest


class ArbitrageEngine:
    """
    Cross-Exchange Arbitrage Monitor.
    Subscribes to the Unified Exchange Manager's orderbook pub/sub stream
    to analyze spread inefficiencies continuously.
    """

    def __init__(self, symbols: list = ["BTC/USDT", "ETH/USDT"]):
        self.symbols = symbols
        self.orderbooks = {
            exchange_id: {symbol: None for symbol in self.symbols}
            for exchange_id in settings.ARBITRAGE_EXCHANGES
        }
        self.orderbook_queue = exchange_manager.subscribe_orderbook()
        self._worker_task = None
        self._on_signal_callback = None

        # Cooldown per symbol to prevent spamming
        self._last_trigger: dict[str, float] = {symbol: 0.0 for symbol in self.symbols}
        self.trigger_cooldown = 30.0  # seconds (increased to save network bandwidth)

    def set_signal_callback(self, callback):
        self._on_signal_callback = callback

    async def start(self):
        """Starts the background worker to process incoming orderbook updates."""
        logger.info(
            f"Starting Arbitrage Engine listening to {settings.ARBITRAGE_EXCHANGES}..."
        )
        self._worker_task = asyncio.create_task(self._process_orderbooks())

    async def _process_orderbooks(self):
        try:
            while True:
                ob_event = await self.orderbook_queue.get()
                exchange_id = ob_event["exchange_id"]
                symbol = ob_event["symbol"]
                orderbook = ob_event["data"]

                self.orderbooks[exchange_id][symbol] = orderbook
                await self._analyze_spread(symbol)

                # Broadcast orderbook to UI
                from core.state import global_state

                asyncio.create_task(
                    global_state._broadcast(
                        {
                            "type": "orderbook",
                            "data": {
                                "asks": orderbook.get("asks", []),
                                "bids": orderbook.get("bids", []),
                            },
                        }
                    )
                )

        except asyncio.CancelledError:
            logger.info("Arbitrage Engine worker cancelled.")
        except Exception as e:
            logger.error(f"Error in Arbitrage Engine _process_orderbooks: {e}")

    async def _analyze_spread(self, symbol: str):
        """
        Compares highest bid and lowest ask across monitored exchanges.
        Identifies if Bid(Exchange A) > Ask(Exchange B) - Fees.

        Assumes a standard trade size of 0.01 for base assets like BTC/ETH.
        """
        best_bids = {}
        best_asks = {}

        for ex_name, books in self.orderbooks.items():
            book = books.get(symbol)
            if book and len(book.get("bids", [])) > 0 and len(book.get("asks", [])) > 0:
                best_bids[ex_name] = book["bids"][0][0]  # [price, amount]
                best_asks[ex_name] = book["asks"][0][0]

        # Compare pairs
        ex_names = list(self.orderbooks.keys())
        for ex_a, ex_b in itertools.permutations(ex_names, 2):
            if ex_a in best_bids and ex_b in best_asks:
                bid_a = best_bids[ex_a]
                ask_b = best_asks[ex_b]

                trade_amount_base = 0.01

                orderbook_buy = self.orderbooks[ex_b].get(symbol)
                orderbook_sell = self.orderbooks[ex_a].get(symbol)

                if orderbook_buy is None or orderbook_sell is None:
                    continue

                # Fast-path pre-check for gross margin
                gross_profit_usd = (bid_a - ask_b) * trade_amount_base
                trade_size_usd = trade_amount_base * ask_b
                gross_margin_pct = (
                    (gross_profit_usd / trade_size_usd) * 100
                    if trade_size_usd > 0
                    else 0.0
                )

                # Minimum threshold for execution
                min_net_margin_pct = 0.05

                # If gross margin is lower than min net margin + rough fee estimate (0.1%), skip heavy calculation
                if gross_margin_pct < min_net_margin_pct + 0.1:
                    continue

                request = ProfitabilityRequest(
                    symbol=symbol,
                    exchange_buy=ex_b,
                    exchange_sell=ex_a,
                    ask_price=ask_b,
                    bid_price=bid_a,
                    trade_amount_base=trade_amount_base,
                    orderbook_buy=orderbook_buy,
                    orderbook_sell=orderbook_sell,
                )
                profit_metrics = ProfitCalculator.calculate_net_profitability(request)

                net_margin_pct = profit_metrics["net_margin_pct"]
                gross_margin_pct = profit_metrics["gross_margin_pct"]
                cex_fees_usd = profit_metrics["cex_fees_usd"]
                slippage_usd = profit_metrics["slippage_usd"]

                if net_margin_pct > min_net_margin_pct:
                    now = time.monotonic()
                    if now - self._last_trigger.get(symbol, 0) > self.trigger_cooldown:
                        self._last_trigger[symbol] = now
                        logger.warning(
                            f"🚨 ARB DETECTED [{symbol}]: Buy on {ex_b} @ {ask_b}, Sell on {ex_a} @ {bid_a} | "
                            f"Gross: {gross_margin_pct:.3f}%, Fees: ${cex_fees_usd:.2f}, Slip: ${slippage_usd:.2f}, Net: {net_margin_pct:.3f}%"
                        )
                        if self._on_signal_callback:
                            # Pass it out to order manager
                            await self._on_signal_callback(
                                symbol, ex_b, ex_a, amount=trade_amount_base
                            )

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
        await exchange_manager.unsubscribe_orderbook(self.orderbook_queue)
