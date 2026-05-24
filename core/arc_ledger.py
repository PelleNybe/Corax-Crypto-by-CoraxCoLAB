import time
from typing import Dict

import requests
from loguru import logger

from core.config import settings

# Arc Network Constants
ARC_RPC_URL_MAINNET = "https://rpc.mainnet.arc.network"
ARC_RPC_URL_TESTNET = "https://rpc.testnet.arc.network"

# FIX: Web3 Services (W3S) API kräver /w3s prefix för Developer Controlled Wallets
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
        self._sync_balance(force=True)

    def _sync_balance(self, force: bool = False):
        """Fetch real USDC balance from Circle Programmable Wallet"""
        if not self.api_key or not self.wallet_id:
            logger.warning("Circle credentials missing i ArcLedger.")
            return

        now = time.monotonic()
        if not force and (now - self._last_sync_time) < self._sync_cooldown:
            return  # Skip sync, use cached balance

        self._last_sync_time = now

        try:
            # FIX: Anropar specifikt balances-endpoint för W3S
            url = f"{self.api_base}/wallets/{self.wallet_id}/balances"

            # Vi lägger till User-Agent för att undvika 403-blockeringar i Docker
            custom_headers = self.headers.copy()
            custom_headers["User-Agent"] = "CoraxCryptoAgent/1.0"

            response = requests.get(url, headers=custom_headers, timeout=5)

            if response.status_code == 200:
                data = response.json().get("data", {})
                token_balances = data.get("tokenBalances", [])

                found_usdc = False
                for b in token_balances:
                    # Circle Testnet/Arc använder ofta 'USDC' som token-symbol
                    symbol = b.get("token", {}).get("symbol", "")
                    if symbol == "USDC" or symbol == "USD":
                        self.balance = float(b.get("amount", 0.0))
                        found_usdc = True
                        break

                if found_usdc:
                    logger.success(
                        f"✅ ArcLedger synced. Balance: {self.balance:,.2f} USDC"
                    )
                else:
                    logger.warning("Synced with Circle, but no USDC balance found.")
                    self.balance = 0.0
            else:
                logger.error(
                    f"❌ Failed to sync Circle balance: {response.status_code} - {response.text}"
                )

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error syncing balance: {e}")
        except Exception as e:
            logger.error(f"Error syncing balance: {e}")

    def reset_ledger(self):
        """Not supported for live ArcLedger."""
        pass

    async def execute_virtual_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        current_price: float = None,
    ):
        """
        Interfacet som anropas av OrderManager.
        I ArcLedger utför vi faktiska on-chain beräkningar här.
        """
        # Uppdatera saldo innan vi kollar täckning (med cooldown)
        self._sync_balance()

        if not current_price:
            from core.state import global_state

            summary = global_state.get_summary()
            current_price = summary.get("last_price", 0.0)

        slippage_pct = 0.001
        exec_price = current_price

        if side.lower() == "buy":
            exec_price = current_price * (1 + slippage_pct)
            trade_cost = amount * exec_price

            if self.balance < trade_cost:
                logger.warning(
                    f"🚨 INSUFFICIENT USDC: Need {trade_cost:.2f}, have {self.balance:.2f}"
                )
                return False

            # Här skulle vi i framtiden kunna trigga en faktisk transfer till en börs via Circle API
            # För tillfället simulerar vi avräkningen mot vårt Arc-saldo
            self.balance -= trade_cost
            self.positions[symbol] = self.positions.get(symbol, 0.0) + amount
            logger.info(
                f"🟢 ARC BUY EXEC: {amount} {symbol} (Cost: {trade_cost:.2f} USDC)"
            )

        elif side.lower() == "sell":
            current_pos = self.positions.get(symbol, 0.0)
            if current_pos < amount:
                logger.warning(
                    f"🚨 INSUFFICIENT ASSET: Trying to sell {amount}, hold {current_pos}"
                )
                return False

            exec_price = current_price * (1 - slippage_pct)
            gain = amount * exec_price

            self.balance += gain
            self.positions[symbol] -= amount
            logger.info(f"🔴 ARC SELL EXEC: {amount} {symbol} (Gain: {gain:.2f} USDC)")

        self.trade_history.append(
            {
                "timestamp": time.time(),
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": exec_price,
                "balance_after": self.balance,
            }
        )
        return True

    # Hjälpmetod för att tvinga en uppdatering utifrån
    async def refresh_balance(self):
        self._sync_balance(force=True)
        return self.balance
