import asyncio
from typing import Any, Dict

from loguru import logger

from core.config import settings
from core.risk_manager import RiskManager
from execution.exchange_manager import exchange_manager
from schemas.signals import AISignal
from execution.bridge_manager import CCTPManager


class OrderManager:
    def __init__(self, risk_manager: RiskManager):
        self.risk_manager = risk_manager
        self.is_dry_run = settings.DRY_RUN_MODE
        self.primary_exchange = settings.EXCHANGE_ID
        self.cctp_manager = CCTPManager()

        if self.is_dry_run:
            if settings.USE_ARC_LEDGER:
                from core.arc_ledger import ArcLedger

                self.paper_ledger = ArcLedger()
            else:
                from core.paper_ledger import PaperLedger

                self.paper_ledger = PaperLedger()
            self.available_balance = self.paper_ledger.balance
            logger.warning("🟢 DRY RUN MODE ACTIVE (ArcLedger Live Settlement Enabled)")
        else:
            self.available_balance = 10000.0
            logger.warning("🔴 LIVE MODE ACTIVE. Real capital is at risk.")

        self.order_queue = asyncio.Queue()
        self.active_limit_orders: Dict[str, Any] = {}
        self._worker_task = asyncio.create_task(self._process_queue())

    async def _process_queue(self):
        """Bakgrundsarbetare som sköter ordrar sekventiellt."""
        logger.info("Starting Async Order Queue Worker...")
        try:
            while True:
                task = await self.order_queue.get()
                action, payload = task
                logger.info(f"Popped task: {action}")

                async def execute_task(action, payload):
                    try:
                        if action == "CREATE":
                            symbol = payload["symbol"]
                            # FIX: Tvinga mikro-storlek för allt i test-läge
                            adj_amount = 0.0001 if "BTC" in symbol else 0.005
                            side = payload["side"]

                            # Fix SELL spam
                            if side.lower() == "sell":
                                if hasattr(self.paper_ledger, "positions"):
                                    current_pos = self.paper_ledger.positions.get(
                                        symbol, 0.0
                                    )
                                    if current_pos <= 0:
                                        logger.debug(
                                            f"Ignoring SELL signal for {symbol} - zero position."
                                        )
                                        return

                            if self.is_dry_run:
                                # Hämta exakt pris för symbolen för att undvika 50k-buggen
                                from core.state import global_state

                                current_price = payload.get("price")
                                if not current_price:
                                    # Fallback till senaste kända priset för JUST denna tillgång
                                    current_price = global_state.get_summary().get(
                                        f"price_{symbol}", payload.get("price", 0.0)
                                    )

                                await self.paper_ledger.execute_virtual_order(
                                    symbol=symbol,
                                    side=payload["side"],
                                    order_type=payload["type"],
                                    amount=adj_amount,
                                    current_price=current_price,
                                )
                                self.available_balance = self.paper_ledger.balance
                                await global_state.update_balance(
                                    self.available_balance
                                )
                            else:
                                await exchange_manager.execute_order(
                                    payload.get("exchange_id", self.primary_exchange),
                                    symbol,
                                    payload["type"],
                                    payload["side"],
                                    adj_amount,
                                    payload.get("price"),
                                )

                        elif action == "CANCEL" and not self.is_dry_run:
                            await exchange_manager.cancel_order(
                                payload.get("exchange_id", self.primary_exchange),
                                payload["order_id"],
                                payload["symbol"],
                            )

                        elif action == "CCTP_TRANSFER":
                            logger.info(
                                f"Popped CCTP_TRANSFER from queue. Payload: {payload}"
                            )
                            logger.info("Awaiting execution of CCTP Transfer...")

                            # We await here to ensure it's not silently dropping
                            success = await self.cctp_manager.execute_full_bridge(
                                amount=payload["amount"],
                                source_chain=payload["source_chain"],
                                target_chain=payload["target_chain"],
                                destination_address=payload["destination_address"],
                            )
                            if success:
                                logger.success(
                                    "✅ CCTP transfer completed successfully and awaited through OrderManager."
                                )
                            else:
                                logger.error("❌ CCTP transfer failed in OrderManager.")

                    except Exception as e:
                        logger.error(
                            f"Error in queue processing for action {action}: {e}"
                        )
                    finally:
                        self.order_queue.task_done()

                # Dispatch as background task so queue isn't blocked by slow I/O
                asyncio.create_task(execute_task(action, payload))
        except asyncio.CancelledError:
            logger.info("Order Queue Worker shutting down.")

    async def execute_signal(self, signal: AISignal):
        is_valid, trade_value = await self.risk_manager.validate_and_size(
            signal, self.available_balance
        )
        if not is_valid:
            return
        await self.order_queue.put(
            (
                "CREATE",
                {
                    "symbol": signal.asset_pair,
                    "type": "market",
                    "side": signal.action.lower(),
                    "amount": trade_value,
                },
            )
        )

    async def requote_market_maker(
        self, symbol: str, bid_price: float, ask_price: float, amount: float
    ):
        if self.risk_manager.kill_switch_active:
            return

        # Rensa gamla limit-ordrar
        for o_id in list(self.active_limit_orders.keys()):
            await self.order_queue.put(("CANCEL", {"order_id": o_id, "symbol": symbol}))

        # Lägg nya mikro-ordrar i kön
        await self.order_queue.put(
            (
                "CREATE",
                {
                    "symbol": symbol,
                    "type": "limit",
                    "side": "buy",
                    "price": bid_price,
                    "amount": amount,
                },
            )
        )
        await self.order_queue.put(
            (
                "CREATE",
                {
                    "symbol": symbol,
                    "type": "limit",
                    "side": "sell",
                    "price": ask_price,
                    "amount": amount,
                },
            )
        )

    async def execute_arbitrage_legs(
        self, symbol: str, buy_exchange: str, sell_exchange: str, amount: float
    ):
        """Huvudmetoden för arbitrage-exekvering."""
        if self.risk_manager.kill_switch_active:
            return

        # FIX: Justera volym för testnet (0.0001 BTC eller 0.005 ETH)
        adj_amount = 0.0001 if "BTC" in symbol else 0.005

        # Hämta live-pris för JUST denna symbol
        try:
            ticker = await exchange_manager.exchanges[buy_exchange].fetch_ticker(symbol)
            actual_price = ticker["last"]
        except Exception:
            actual_price = 0.0

        logger.info(
            f"⚡ ARB EXEC: {adj_amount} {symbol} ({buy_exchange} -> {sell_exchange} @ {actual_price})"
        )

        if self.is_dry_run:
            # Exekvera direkt mot ledger med rätt pris
            await self.paper_ledger.execute_virtual_order(
                symbol, "buy", "market", adj_amount, actual_price
            )
            await self.paper_ledger.execute_virtual_order(
                symbol, "sell", "market", adj_amount, actual_price
            )
            self.available_balance = self.paper_ledger.balance
            return

        # Vid LIVE exekvering (när du ändrar i .env senare)
        await asyncio.gather(
            exchange_manager.execute_order(
                buy_exchange, symbol, "market", "buy", adj_amount
            ),
            exchange_manager.execute_order(
                sell_exchange, symbol, "market", "sell", adj_amount
            ),
            return_exceptions=True,
        )

    async def execute_cctp_transfer(
        self,
        amount: float,
        source_chain: str,
        target_chain: str,
        destination_address: str,
    ):
        """
        Public method to enqueue a CCTP transfer, usually called by the copilot or AI engine.
        """
        await self.order_queue.put(
            (
                "CCTP_TRANSFER",
                {
                    "amount": amount,
                    "source_chain": source_chain,
                    "target_chain": target_chain,
                    "destination_address": destination_address,
                },
            )
        )

    async def shutdown(self):
        if self._worker_task:
            self._worker_task.cancel()
