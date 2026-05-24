from loguru import logger
from typing import Dict


class PaperLedger:
    """
    Virtual Ledger for Paper Trading.
    Simulates accurate trade execution against live market feeds without committing real capital.
    Calculates fees and dynamic slippage.
    """

    def __init__(
        self,
        initial_capital: float = None,
        maker_fee: float = 0.0002,
        taker_fee: float = 0.0005,
    ):
        from core.config import settings

        if initial_capital is None:
            initial_capital = settings.PAPER_BALANCE_USDT
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.positions: Dict[str, float] = {}  # symbol -> amount
        self.trade_history = []

        logger.info(
            f"Initialized PaperLedger. Virtual Capital: ${initial_capital:,.2f}"
        )

    def reset_ledger(self):
        """Resets the ledger balance to the initial capital and wipes history."""
        self.balance = self.initial_capital
        self.positions.clear()
        self.trade_history.clear()
        logger.info(
            f"📃 LEDGER RESET: Virtual Capital restored to ${self.initial_capital:,.2f}. History wiped."
        )

    def _simulate_slippage(self, order_type: str, amount: float) -> float:
        """
        Calculates dynamic slippage.
        In a fully connected environment, this would parse the actual Level 2 order book depth
        from the ArbitrageEngine to calculate exact VWAP slippage.
        We use a heuristic model here for large market orders.
        """
        if order_type == "limit":
            return 0.0  # No slippage on limit orders (assuming they fill exactly or not at all)

        # Base slippage of 0.05% + impact based on trade size
        base_slippage = 0.0005
        # Assume 1 million is highly liquid, 10k is standard.
        # (Very simplified heuristic for paper trading example)
        volume_impact = (amount / 100000.0) * 0.001

        total_slippage = base_slippage + volume_impact
        return min(total_slippage, 0.02)  # Cap at 2%

    async def execute_virtual_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        current_price: float = None,
    ):
        """
        Executes a virtual trade, updates balances and records the history.
        """
        if not current_price:
            from core.state import global_state

            # Fallback to fetching latest price from state if not provided
            summary = global_state.get_summary()
            current_price = summary.get("last_price", 50000.0)

        slippage_pct = self._simulate_slippage(order_type, amount)
        fee_rate = self.maker_fee if order_type == "limit" else self.taker_fee

        if side.lower() == "buy":
            exec_price = current_price * (1 + slippage_pct)
            trade_cost = amount * exec_price
            fee = trade_cost * fee_rate
            total_deduction = trade_cost + fee

            if self.balance < total_deduction:
                logger.warning(
                    f"DRY RUN INSUFFICIENT FUNDS: Need {total_deduction}, have {self.balance}"
                )
                return False

            self.balance -= total_deduction
            self.positions[symbol] = self.positions.get(symbol, 0.0) + amount

            logger.info(
                f"📃 DRY RUN BUY {amount} {symbol} @ {exec_price:.2f} (Fee: ${fee:.2f}, Slip: {slippage_pct * 100:.3f}%)"
            )

        elif side.lower() == "sell":
            # Check inventory (can allow shorting by tracking negative positions, but we'll stick to spot logic for now)
            current_pos = self.positions.get(symbol, 0.0)
            if current_pos < amount:
                logger.warning(
                    f"DRY RUN INSUFFICIENT ASSET: Trying to sell {amount}, hold {current_pos}"
                )
                return False

            exec_price = current_price * (1 - slippage_pct)
            gross_proceeds = amount * exec_price
            fee = gross_proceeds * fee_rate
            net_proceeds = gross_proceeds - fee

            self.balance += net_proceeds
            self.positions[symbol] -= amount

            logger.info(
                f"📃 DRY RUN SELL {amount} {symbol} @ {exec_price:.2f} (Fee: ${fee:.2f}, Slip: {slippage_pct * 100:.3f}%)"
            )

        self.trade_history.append(
            {
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "amount": amount,
                "exec_price": exec_price,
                "fee": fee,
            }
        )

        return True
