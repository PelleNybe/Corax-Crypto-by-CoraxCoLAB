import aiofiles
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from loguru import logger

from schemas.orders import OrderContext, GridState, GridLine


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
        Path("./data").mkdir(parents=True, exist_ok=True)

        self.journal_path = Path("./data") / "trade_journal.json"

        # Native Grid Tracking
        self.active_grids: Dict[str, GridState] = {}

        self.journal_queue = asyncio.Queue()
        self._journal_task = asyncio.create_task(self._process_journal_queue())

    async def _process_journal_queue(self):
        while True:
            try:
                entry = await self.journal_queue.get()
                journal = []
                if self.journal_path.exists():
                    try:
                        async with aiofiles.open(self.journal_path, "r") as f:
                            file_content = await f.read()
                            journal = json.loads(file_content) if file_content else []
                    except Exception as e:
                        logger.error(f"Error reading journal {self.journal_path}: {e}")
                        journal = []

                journal.append(entry)
                if len(journal) > 100:
                    journal = journal[-100:]

                async with aiofiles.open(self.journal_path, "w") as f:
                    await f.write(json.dumps(journal, indent=2))

                self.journal_queue.task_done()
            except asyncio.CancelledError:
                logger.info("Trade Journal Worker shutting down.")
                break
            except Exception as e:
                logger.error(f"Error in journal worker: {e}")

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
                "timestamp": datetime.now().astimezone().isoformat() + "Z",
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": price,
                "regime": global_state.current_regime,
                "rationale": rationale,
            }

            await self.journal_queue.put(entry)

            logger.success(f"📝 Trade Journal Updated: {side} {symbol} - {rationale}")

        except Exception as e:
            logger.error(f"Failed to log trade rationale: {e}")

    def _get_testnet_amount(
        self, symbol: str, price: float = 0.0, *exchange_ids: str
    ) -> float:
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
                min_cost = market.get("limits", {}).get("cost", {}).get("min")

                # If we have price and min_cost, ensure amount is at least min_cost / price
                calc_amount = None
                if min_cost is not None and price > 0:
                    calc_amount = (min_cost / price) * 1.05  # 5% buffer

                if min_amount is not None and calc_amount is not None:
                    return max(min_amount, calc_amount)
                elif min_amount is not None:
                    return min_amount
                elif calc_amount is not None:
                    return calc_amount

        # Dynamic fallback based on price, assuming $10 notional value to be safe but small
        if price > 0:
            return (10.0 / price) * 1.05

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
                            # SAFETY: Universally force micro-sizes in testnet mode via dynamic adjustment. This behavior is hardcoded for safety.
                            if settings.CORAX_MODE.lower() == "testnet":
                                exchange_id = payload.get(
                                    "exchange_id", self.primary_exchange
                                )

                                # Resolve price early for dynamic volume calculation
                                current_price = payload.get("price")
                                if not current_price:
                                    from core.state import global_state

                                    current_price = global_state.get_summary().get(
                                        f"price_{symbol}", 0.0
                                    )

                                adj_amount = self._get_testnet_amount(
                                    symbol, current_price, exchange_id
                                )
                            else:
                                adj_amount = payload.get("amount", 0.0)
                            side = payload["side"]

                            # Fix SELL spam
                            # Only apply position-based capping to market orders to avoid blocking grid/MM limit orders
                            if (
                                side.lower() == "sell"
                                and payload.get("type", "market").lower() == "market"
                            ):
                                current_pos = 0.0
                                if self.is_dry_run:
                                    if hasattr(self.paper_ledger, "positions"):
                                        current_pos = self.paper_ledger.positions.get(
                                            symbol, 0.0
                                        )
                                else:
                                    if (
                                        hasattr(self.risk_manager, "active_positions")
                                        and symbol in self.risk_manager.active_positions
                                    ):
                                        current_pos = (
                                            self.risk_manager.active_positions[
                                                symbol
                                            ].get("amount", 0.0)
                                        )

                                # Dust threshold to prevent SELL spam for tiny leftover amounts
                                dust_threshold = 1e-6
                                if current_pos <= dust_threshold:
                                    logger.debug(
                                        f"Ignoring SELL signal for {symbol} - position ({current_pos}) is zero or dust."
                                    )
                                    # Clean up dust from ledger if applicable
                                    if self.is_dry_run:
                                        if (
                                            hasattr(self.paper_ledger, "positions")
                                            and symbol in self.paper_ledger.positions
                                        ):
                                            self.paper_ledger.positions[symbol] = 0.0
                                    else:
                                        # Call the async method safely, we are already in an async context here inside _process_queue inner execute_task
                                        await self.risk_manager.clear_position(symbol)
                                    return

                                # Sometimes testnet amount recalculates to a micro size (e.g. 0.00021).
                                # But if we received a signal to sell a large amount (like we want to close position),
                                # we should sell all of what we have. We should override the testnet adjustment for sells
                                # so we don't leave dust behind and keep spamming SELLs for the remaining amount.
                                if (
                                    settings.CORAX_MODE.lower() == "testnet"
                                    and payload.get("amount", 0.0) >= current_pos
                                ):
                                    adj_amount = current_pos

                                # If the target sell amount is larger than our holding, or if it's testnet
                                # forcing a micro-size but we want to clear out our remaining holding.
                                # Let's cap the sell amount to avoid Insufficient Funds errors due to fees,
                                # and properly clear positions without spamming if they fall just below testnet threshold.
                                adj_amount = min(adj_amount, current_pos)

                                # If the remaining position would be less than dust, sell it all
                                if (current_pos - adj_amount) <= dust_threshold:
                                    adj_amount = current_pos

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
                                    OrderContext(
                                        symbol=symbol,
                                        side=payload["side"],
                                        order_type=payload["type"],
                                        amount=adj_amount,
                                        current_price=current_price,
                                    )
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
                                # Futures / Institutional reduceOnly handling
                                exec_params = {}
                                if (
                                    settings.MARKET_TYPE in ["future", "swap"]
                                    and side.lower() == "sell"
                                ):
                                    # If selling an active position in futures, it's a reduceOnly close
                                    exec_params["reduceOnly"] = True

                                context = OrderContext(
                                    symbol=symbol,
                                    side=payload["side"],
                                    order_type=payload["type"],
                                    amount=adj_amount,
                                    current_price=payload.get("price"),
                                )
                                result = await exchange_manager.execute_order(
                                    payload.get("exchange_id", self.primary_exchange),
                                    context,
                                    params=exec_params,
                                )

                                if result:
                                    await self._log_trade_rationale(
                                        symbol,
                                        side,
                                        adj_amount,
                                        payload.get("price", 0.0),
                                    )
                                    if (
                                        side.lower() == "sell"
                                        and payload.get("type", "market").lower()
                                        == "market"
                                    ):
                                        # Clear position from risk_manager if we sold everything (or left with dust)
                                        if (current_pos - adj_amount) <= dust_threshold:
                                            if hasattr(self, "risk_manager"):
                                                await self.risk_manager.clear_position(
                                                    symbol
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

    async def initialize_grid(
        self,
        symbol: str,
        current_price: float,
        total_investment: float,
        grid_lines: list[dict],
    ):
        """
        Deploys an entire Grid of limit orders to the exchange.
        """
        if symbol in self.active_grids:
            logger.warning(f"Grid already active for {symbol}. Cancel it first.")
            return

        logger.info(f"Deploying Grid for {symbol} with {len(grid_lines)} lines...")
        state = GridState(symbol=symbol, lines=[])

        for line in grid_lines:
            # Queue creation of limit order
            await self.order_queue.put(
                (
                    "CREATE",
                    {
                        "symbol": symbol,
                        "type": "limit",
                        "side": line["side"],
                        "price": line["price"],
                        "amount": line["amount"],
                    },
                )
            )

            # We track the intent. In a real system, we capture the ID from the exchange response
            state.lines.append(
                GridLine(
                    price=line["price"],
                    side=line["side"],
                    amount=line["amount"],
                    is_active=True,
                )
            )

        self.active_grids[symbol] = state
        logger.success(f"Grid deployed and tracked for {symbol}.")

        # Start a background task to watch this grid's orders
        if not self.is_dry_run:
            asyncio.create_task(self._monitor_grid(symbol))

    async def _monitor_grid(self, symbol: str):
        """Monitors a grid via CCXT watch_orders and replaces filled limits."""
        from execution.exchange_manager import exchange_manager

        ex = exchange_manager.exchanges.get(self.primary_exchange)
        if not ex:
            return

        try:
            while symbol in self.active_grids:
                orders = await ex.watch_orders(symbol)
                state = self.active_grids.get(symbol)
                if not state:
                    break

                for order in orders:
                    if order["status"] in ["closed", "filled"]:
                        # Find the corresponding grid line
                        filled_price = order.get("price")
                        filled_side = order.get("side")

                        logger.info(
                            f"Grid order filled: {filled_side} {symbol} @ {filled_price}"
                        )

                        closest_line = None
                        min_diff = float("inf")
                        for line in state.lines:
                            diff = abs(line.price - filled_price)
                            if diff < min_diff and line.side == filled_side:
                                min_diff = diff
                                closest_line = line

                        if closest_line:
                            # Reverse the side and dispatch a new order slightly above/below
                            new_side = "sell" if filled_side == "buy" else "buy"

                            # Retrieve step size dynamically from settings
                            grid_step = (
                                settings.GRID_UPPER_PRICE - settings.GRID_LOWER_PRICE
                            ) / max(1, (settings.GRID_LEVELS - 1))
                            offset = grid_step if new_side == "sell" else -grid_step

                            new_price = filled_price + offset

                            closest_line.side = new_side
                            closest_line.price = new_price

                            await self.order_queue.put(
                                (
                                    "CREATE",
                                    {
                                        "symbol": symbol,
                                        "type": "limit",
                                        "side": new_side,
                                        "price": new_price,
                                        "amount": closest_line.amount,
                                    },
                                )
                            )
                            logger.success(
                                f"Grid rebalancing: Replaced {filled_side} with {new_side} @ {new_price}"
                            )

        except Exception as e:
            logger.error(f"Grid monitoring error for {symbol}: {e}")
            await asyncio.sleep(5)
            if symbol in self.active_grids:
                asyncio.create_task(self._monitor_grid(symbol))

    async def execute_signal(self, signal: AISignal):
        import json

        is_valid, trade_value = await self.risk_manager.validate_and_size(
            signal, self.available_balance
        )
        if not is_valid:
            return

        # Execute for main account
        order_params = {}
        if (
            settings.MARKET_TYPE in ["future", "swap"]
            and signal.action.lower() == "sell"
            and getattr(self, "available_balance", 0) > 0
        ):
            order_params["reduceOnly"] = True

        await self.order_queue.put(
            (
                "CREATE",
                {
                    "exchange_id": settings.EXCHANGE_ID,
                    "symbol": signal.asset_pair,
                    "type": "market",
                    "side": signal.action.lower(),
                    "amount": trade_value,
                    **order_params,
                },
            )
        )

        # Execute for copy-trade accounts
        if settings.COPY_TRADE_ENABLED:
            try:
                multi_cfg = json.loads(settings.MULTI_ACCOUNT_CONFIG)
                from execution.exchange_manager import exchange_manager

                async def process_sub_account(account_id, creds):
                    if "exchange" not in creds:
                        return

                    acc_key = f"{creds['exchange']}_{account_id}"

                    # Fetch sub-account balance to size proportionally
                    sub_balance = getattr(self, "available_balance", 0.0)  # fallback
                    sub_ex = exchange_manager.exchanges.get(acc_key)
                    if sub_ex and not getattr(self, "is_dry_run", False):
                        try:
                            balance_data = await sub_ex.fetch_balance()
                            sub_balance = balance_data.get("total", {}).get("USDT", 0.0)
                        except Exception as e:
                            from loguru import logger

                            logger.warning(
                                f"Could not fetch balance for {acc_key}: {e}"
                            )

                    (
                        is_sub_valid,
                        sub_trade_value,
                    ) = await self.risk_manager.validate_and_size(signal, sub_balance)

                    if is_sub_valid and sub_trade_value > 0:
                        await self.order_queue.put(
                            (
                                "CREATE",
                                {
                                    "exchange_id": acc_key,
                                    "symbol": signal.asset_pair,
                                    "type": "market",
                                    "side": signal.action.lower(),
                                    "amount": sub_trade_value,
                                    **order_params,
                                },
                            )
                        )

                tasks = [
                    process_sub_account(account_id, creds)
                    for account_id, creds in multi_cfg.items()
                ]
                if tasks:
                    import asyncio

                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for result in results:
                        if isinstance(result, Exception):
                            from loguru import logger

                            logger.error(
                                f"Copy trade multi-routing subtask failed: {result}"
                            )

            except Exception as e:
                from loguru import logger

                logger.error(f"Copy trade multi-routing failed: {e}")

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

        # Hämta live-pris för JUST denna symbol
        try:
            ticker = await exchange_manager.exchanges[buy_exchange].fetch_ticker(symbol)
            actual_price = ticker["last"]
        except Exception:
            actual_price = 0.0

        if settings.CORAX_MODE.lower() == "testnet":
            adj_amount = self._get_testnet_amount(
                symbol, actual_price, buy_exchange, sell_exchange
            )
        else:
            adj_amount = amount

        logger.info(
            f"⚡ ARB EXEC: {adj_amount} {symbol} ({buy_exchange} -> {sell_exchange} @ {actual_price})"
        )

        if self.is_dry_run:
            # Exekvera direkt mot ledger med rätt pris
            await self.paper_ledger.execute_virtual_order(
                OrderContext(
                    symbol=symbol,
                    side="buy",
                    order_type="market",
                    amount=adj_amount,
                    current_price=actual_price,
                )
            )
            await self.paper_ledger.execute_virtual_order(
                OrderContext(
                    symbol=symbol,
                    side="sell",
                    order_type="market",
                    amount=adj_amount,
                    current_price=actual_price,
                )
            )
            self.available_balance = self.paper_ledger.balance

            # Log rationale
            await self._log_trade_rationale(
                symbol, "buy_arbitrage", adj_amount, actual_price
            )
            return

        # Vid LIVE exekvering (när du ändrar i .env senare)
        buy_context = OrderContext(
            symbol=symbol,
            side="buy",
            order_type="market",
            amount=adj_amount,
            current_price=actual_price,
        )
        sell_context = OrderContext(
            symbol=symbol,
            side="sell",
            order_type="market",
            amount=adj_amount,
            current_price=actual_price,
        )
        results = await asyncio.gather(
            exchange_manager.execute_order(buy_exchange, buy_context),
            exchange_manager.execute_order(sell_exchange, sell_context),
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
        if hasattr(self, "_journal_task") and self._journal_task:
            self._journal_task.cancel()

    async def _place_order_internal(
        self,
        context: OrderContext,
    ) -> dict:
        order_res = await exchange_manager.execute_order(
            exchange_id=self.primary_exchange, context=context
        )
        return order_res
