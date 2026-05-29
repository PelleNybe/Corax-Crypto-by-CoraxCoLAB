import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict

from loguru import logger

from core.config import settings
from core.risk_manager import RiskManager
from execution.exchange_manager import exchange_manager
from schemas.signals import AISignal
from execution.bridge_manager import CCTPManager
from intelligence.copilot import CoraxCopilot


class OrderManager:
    def __init__(self, risk_manager: RiskManager):
        self.risk_manager = risk_manager
        self.is_dry_run = settings.DRY_RUN_MODE
        self.primary_exchange = settings.EXCHANGE_ID
        self.cctp_manager = CCTPManager()
        self.copilot = CoraxCopilot()  # For World-Class Feature 4

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

        # Ensure data dir exists for journal
        os.makedirs("./data", exist_ok=True)
        self.journal_path = os.path.join("./data", "trade_journal.json")

    async def _log_trade_rationale(
        self, symbol: str, side: str, amount: float, price: float
    ):
        """
        World-Class Feature 4: Autonomous Trade Rationale Journaling
        Generates a rationale for the trade using the Copilot and saves it to a JSON journal.
        """
        try:
            from core.state import global_state

            # Construct context
            state_summary = {
                "regime": global_state.current_regime,
                "recent_action": side,
                "symbol": symbol,
                "amount": amount,
                "price": price,
                "balance": self.available_balance,
            }

            # Request synthesis
            rationale = await self.copilot.generate_synthesis(state_summary)

            entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": price,
                "regime": global_state.current_regime,
                "rationale": rationale,
            }

            # Load existing
            journal = []
            if os.path.exists(self.journal_path):
                with open(self.journal_path, "r") as f:
                    try:
                        journal = json.load(f)
                    except json.JSONDecodeError:
                        pass

            journal.append(entry)

            # Keep last 100
            if len(journal) > 100:
                journal = journal[-100:]

            with open(self.journal_path, "w") as f:
                json.dump(journal, f, indent=2)

            logger.success(f"📝 Trade Journal Updated: {side} {symbol} - {rationale}")

        except Exception as e:
            logger.error(f"Failed to log trade rationale: {e}")

    def _get_testnet_amount(self, symbol: str, *exchange_ids: str) -> float:
        """Helper method to dynamically determine micro-size amounts for testnet mode."""
        for ex_id in exchange_ids:
            if not ex_id:
                continue
            if (
                ex_id in exchange_manager.exchanges
                and symbol in exchange_manager.exchanges[ex_id].markets
            ):
                market = exchange_manager.exchanges[ex_id].markets[symbol]
                min_amount = market.get("limits", {}).get("amount", {}).get("min")
                if min_amount is not None:
                    return min_amount

        if "BTC" in symbol:
            return 0.0001
        elif "ETH" in symbol:
            return 0.001
        else:
            return 0.005

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
                            if settings.CORAX_MODE.lower() == "testnet":
                                exchange_id = payload.get("exchange_id", self.primary_exchange)
                                adj_amount = self._get_testnet_amount(symbol, exchange_id)
                            else:
                                adj_amount = payload.get("amount", 0.0)
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
                                # Log rationale
                                await self._log_trade_rationale(
                                    symbol, side, adj_amount, current_price
                                )

                            else:
                                result = await exchange_manager.execute_order(
                                    payload.get("exchange_id", self.primary_exchange),
                                    symbol,
                                    payload["type"],
                                    payload["side"],
                                    adj_amount,
                                    payload.get("price"),
                                )
                                if result:
                                    await self._log_trade_rationale(
                                        symbol,
                                        side,
                                        adj_amount,
                                        payload.get("price", 0.0),
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

        # FIX: Justera volym för testnet dynamically
        if settings.CORAX_MODE.lower() == "testnet":
            adj_amount = self._get_testnet_amount(symbol, buy_exchange, sell_exchange)
        else:
            adj_amount = amount

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

            # Log rationale
            await self._log_trade_rationale(
                symbol, "buy_arbitrage", adj_amount, actual_price
            )
            return

        # Vid LIVE exekvering (när du ändrar i .env senare)
        results = await asyncio.gather(
            exchange_manager.execute_order(
                buy_exchange, symbol, "market", "buy", adj_amount
            ),
            exchange_manager.execute_order(
                sell_exchange, symbol, "market", "sell", adj_amount
            ),
            return_exceptions=True,
        )
        if not isinstance(results[0], Exception):
            await self._log_trade_rationale(
                symbol, "buy_arbitrage", adj_amount, actual_price
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
