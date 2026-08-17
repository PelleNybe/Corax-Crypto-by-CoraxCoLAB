import time
import asyncio
from typing import Dict
from schemas.orders import OrderContext

import aiohttp
from loguru import logger

from core.config import settings

# Arc Network Constants
ARC_RPC_URL_MAINNET = "https://rpc.mainnet.arc.network"
ARC_RPC_URL_TESTNET = "https://rpc.testnet.arc.network"

# Web3 Services (W3S) API kräver /w3s prefix för Developer Controlled Wallets
CIRCLE_API_BASE_MAINNET = "https://api.circle.com/v1/w3s"
CIRCLE_API_BASE_TESTNET = "https://api.circle.com/v1/w3s"


class ArcLedger:
    """
    ArcLedger connects to the Arc L1 blockchain using Circle's Developer platform.
    It replaces the PaperLedger interface with live USDC settlement.
    """

    def __init__(self, initial_capital: float = None):
        self.api_key = settings.CIRCLE_API_KEY
        self.wallet_id = settings.CIRCLE_WALLET_ID
        self.entity_secret = settings.CIRCLE_ENTITY_SECRET

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Kontrollera om vi är i testnet-läge
        self.is_testnet = (
            settings.CORAX_MODE.lower() == "development"
            or settings.CORAX_MODE.lower() == "testnet"
        )
        self.api_base = (
            CIRCLE_API_BASE_TESTNET if self.is_testnet else CIRCLE_API_BASE_MAINNET
        )
        self.rpc_url = ARC_RPC_URL_TESTNET if self.is_testnet else ARC_RPC_URL_MAINNET

        self.balance = 0.0
        self.positions: Dict[str, float] = {}
        self.trade_history = []

        self._last_sync_time = 0.0
        self._sync_cooldown = 15.0  # seconds

        logger.info(
            f"Initialized ArcLedger (Mode: {'Testnet' if self.is_testnet else 'Mainnet'})"
        )

        # Synka saldo direkt vid start
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._sync_balance(force=True))
        except RuntimeError:
            self._sync_balance_sync(force=True)

    def _process_balance_response(self, data: dict):
        token_balances = data.get("tokenBalances", [])

        found_usdc = False
        valid_symbols = {"USDC", "USD"}
        for b in token_balances:
            try:
                if b["token"]["symbol"] in valid_symbols:
                    self.balance = float(b["amount"])
                    found_usdc = True
                    break
            except KeyError:
                continue

        if found_usdc:
            logger.success(f"✅ ArcLedger synced. Balance: {self.balance:,.2f} USDC")
        else:
            logger.warning("Synced with Circle, but no USDC balance found.")
            self.balance = 0.0

    def _sync_balance_sync(self, force: bool = False):
        if not self.api_key or not self.wallet_id:
            logger.warning("Circle credentials missing i ArcLedger.")
            return

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._sync_balance(force))
        except RuntimeError:
            asyncio.run(self._sync_balance(force))

    async def _sync_balance(self, force: bool = False):
        if not self.api_key or not self.wallet_id:
            logger.warning("Circle credentials missing i ArcLedger.")
            return

        now = time.monotonic()
        if not force and (now - self._last_sync_time) < self._sync_cooldown:
            return

        self._last_sync_time = now

        try:
            url = f"{self.api_base}/wallets/{self.wallet_id}/balances"
            custom_headers = self.headers.copy()
            custom_headers["User-Agent"] = "CoraxCryptoAgent/1.0"

            async with aiohttp.ClientSession(headers=custom_headers) as session:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        json_resp = await response.json()
                        data = json_resp.get("data", {})
                        self._process_balance_response(data)
                    else:
                        text = await response.text()
                        logger.error(
                            f"❌ Failed to sync Circle balance: {response.status} - {text}"
                        )
        except Exception as e:
            logger.error(f"Error syncing balance: {e}")

    def reset_ledger(self):
        """Not supported for live ArcLedger."""
        raise NotImplementedError("reset_ledger is not supported for live ArcLedger.")

    async def execute_virtual_order(
        self,
        context: OrderContext,
    ):
        """

        Interfacet som anropas av OrderManager.
        I ArcLedger utför vi faktiska on-chain beräkningar här.
        """
        # Uppdatera saldo innan vi kollar täckning (med cooldown)
        await self._sync_balance()

        if not context.current_price:
            from core.state import global_state

            summary = global_state.get_summary()
            context.current_price = summary.get(f"price_{context.symbol}", 0.0)

        if context.current_price <= 0:
            logger.warning(
                f"🚨 INVALID PRICE: Cannot execute order with price {context.current_price}"
            )
            return False

        slippage_pct = 0.001
        exec_price = context.current_price

        if context.side.lower() == "buy":
            exec_price = context.current_price * (1 + slippage_pct)
            trade_cost = context.amount * exec_price

            if self.balance < trade_cost:
                logger.warning(
                    f"🚨 INSUFFICIENT USDC: Need {trade_cost:.2f}, have {self.balance:.2f}"
                )
                return False

            # Här skulle vi i framtiden kunna trigga en faktisk transfer till en börs via Circle API
            # För tillfället simulerar vi avräkningen mot vårt Arc-saldo
            self.balance -= trade_cost
            self.positions[context.symbol] = (
                self.positions.get(context.symbol, 0.0) + context.amount
            )
            logger.info(
                f"🟢 ARC BUY EXEC: {context.amount} {context.symbol} (Cost: {trade_cost:.2f} USDC)"
            )

        elif context.side.lower() == "sell":
            current_pos = self.positions.get(context.symbol, 0.0)
            if current_pos < context.amount:
                logger.warning(
                    f"🚨 INSUFFICIENT ASSET: Trying to sell {context.amount}, hold {current_pos}"
                )
                return False

            exec_price = context.current_price * (1 - slippage_pct)
            gain = context.amount * exec_price

            self.balance += gain
            self.positions[context.symbol] -= context.amount
            logger.info(
                f"🔴 ARC SELL EXEC: {context.amount} {context.symbol} (Gain: {gain:.2f} USDC)"
            )
        else:
            logger.warning(f"🚨 INVALID ORDER SIDE: {context.side}")
            return False

        self.trade_history.append(
            {
                "timestamp": time.time(),
                "symbol": context.symbol,
                "side": context.side,
                "amount": context.amount,
                "price": exec_price,
                "balance_after": self.balance,
            }
        )
        return True

    # Hjälpmetod för att tvinga en uppdatering utifrån
    async def refresh_balance(self):
        await self._sync_balance(force=True)
        return self.balance
