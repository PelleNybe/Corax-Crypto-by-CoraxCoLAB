import datetime
import asyncio
from typing import Tuple, Dict

from loguru import logger

from core.config import settings
from schemas.signals import AISignal


class RiskManager:
    """
    Handles dynamic position sizing, Trailing Stop-Loss (TSL), and protects capital via daily drawdown kill switches.
    Includes a time-based reset for peak balance at UTC midnight.
    """

    def __init__(self):
        self.max_risk_per_trade = settings.MAX_RISK_PER_TRADE_PCT
        self.max_daily_drawdown = settings.DAILY_DRAWDOWN_LIMIT_PCT

        # Position tracking for Trailing Stop Loss
        self.active_positions: Dict[str, dict] = {}
        # Trailing stop configuration: percent drop from peak allowed
        self.trailing_stop_pct = 0.02  # 2% trailing stop

        # Sync baseline
        self.peak_balance = 0.0
        self.initial_sync_done = False

        self.kill_switch_active = False
        self.last_reset_date = datetime.datetime.now(datetime.timezone.utc).date()
        self._lock = asyncio.Lock()

    async def _check_daily_reset(self, current_balance: float):
        """Resets the peak balance and kill switch at UTC midnight."""
        current_date = datetime.datetime.now(datetime.timezone.utc).date()
        if current_date > self.last_reset_date:
            logger.info(
                f"UTC Midnight Reset: Updating peak_balance from {self.peak_balance} to {current_balance} and disabling Kill Switch."
            )
            self.peak_balance = current_balance
            self.kill_switch_active = False
            self.last_reset_date = current_date

    async def register_position(self, symbol: str, entry_price: float, amount: float):
        """Registers a new active position for trailing stop monitoring."""
        self.active_positions[symbol] = {
            "entry_price": entry_price,
            "amount": amount,
            "high_watermark": entry_price,
            "trailing_stop_price": entry_price * (1 - self.trailing_stop_pct),
        }
        logger.debug(
            f"Registered position {symbol} at {entry_price} with TSL at {self.active_positions[symbol]['trailing_stop_price']}"
        )

    async def clear_position(self, symbol: str):
        """Clears a position from tracking (e.g., after it is sold)."""
        if symbol in self.active_positions:
            del self.active_positions[symbol]
            logger.debug(f"Cleared position tracking for {symbol}")

    async def check_trailing_stops(self, symbol: str, current_price: float) -> bool:
        """
        Updates the high watermark and checks if the trailing stop has been hit.
        Returns True if a SELL signal should be forced to stop out the position.
        """
        if symbol not in self.active_positions:
            return False

        pos = self.active_positions[symbol]

        # Update high watermark if price increases
        if current_price > pos["high_watermark"]:
            pos["high_watermark"] = current_price
            new_tsl = current_price * (1 - self.trailing_stop_pct)

            # Only trail upwards
            if new_tsl > pos["trailing_stop_price"]:
                pos["trailing_stop_price"] = new_tsl
                logger.debug(f"[{symbol}] Trailing stop updated to {new_tsl:.2f}")

        # Check if current price breached the trailing stop line
        if current_price <= pos["trailing_stop_price"]:
            logger.warning(
                f"🚨 TSL TRIGGERED for {symbol}: Price {current_price:.2f} fell below stop {pos['trailing_stop_price']:.2f}"
            )
            return True

        return False

    async def validate_and_size(
        self, signal: AISignal, current_balance: float
    ) -> Tuple[bool, float]:
        """
        Validates the signal against risk parameters and calculates trade size.
        """
        async with self._lock:
            # 1. Sync peak_balance
            if not self.initial_sync_done and current_balance > 0:
                self.peak_balance = current_balance
                self.initial_sync_done = True
                logger.success(
                    f"🛡️ RiskManager baseline synchronized to real balance: ${current_balance:.2f} USDC"
                )

            await self._check_daily_reset(current_balance)

            # 2. Update peak_balance
            if current_balance > self.peak_balance:
                self.peak_balance = current_balance
                if self.kill_switch_active:
                    logger.info("New peak balance reached. Disabling Kill Switch.")
                    self.kill_switch_active = False

            # 3. Calculate Drawdown
            if self.peak_balance > 0:
                current_drawdown = max(
                    0.0, (self.peak_balance - current_balance) / self.peak_balance
                )
                if current_drawdown >= self.max_daily_drawdown:
                    if not self.kill_switch_active:
                        logger.warning(
                            f"🚨 KILL SWITCH ACTIVATED: Drawdown {current_drawdown:.2%} exceeds max {self.max_daily_drawdown:.1%}"
                        )
                        self.kill_switch_active = True

            # 4. Check Kill Switch
            if self.kill_switch_active:
                # Block buys, allow sells
                if signal.action == "BUY":
                    logger.debug("Signal rejected: Kill Switch is active.")
                    return False, 0.0

            if signal.action == "HOLD":
                return False, 0.0

            # 5. Calculate position size
            trade_value = current_balance * self.max_risk_per_trade

            return True, trade_value

    async def manual_reset(self, current_balance: float):
        """Helper to force a reset (e.g. via Telegram)."""
        self.peak_balance = current_balance
        self.kill_switch_active = False
        self.initial_sync_done = True
        logger.success(
            f"🛡️ RiskManager manually reset. New baseline: ${current_balance:.2f} USDC"
        )
