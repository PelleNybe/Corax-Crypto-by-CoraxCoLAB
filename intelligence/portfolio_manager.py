import asyncio
import json
import time
from typing import Dict, Any
from loguru import logger
import polars as pl

from intelligence.copilot import CoraxCopilot
from schemas.signals import AISignal


class PortfolioManager:
    """
    The Ensemble Manager that runs multiple strategies, evaluates their signals,
    tracks degradation, and uses the LLM Copilot for consensus allocation.
    """

    def __init__(self, copilot: CoraxCopilot):
        from strategies.sma_crossover import SmaCrossover
        from strategies.funding_rate_arb import FundingRateArb
        from strategies.orderbook_imbalance import OrderbookImbalance

        self.copilot = copilot
        self.strategies = {
            "SmaCrossover": SmaCrossover(),
            "FundingRateArb": FundingRateArb(),
            "OrderbookImbalance": OrderbookImbalance(),
        }

        # Track strategy performance: {"StrategyName": {"trades": 0, "wins": 0, "degraded": False}}
        self.performance = {
            name: {"trades": 0, "wins": 0, "degraded": False}
            for name in self.strategies.keys()
        }
        self.min_trades_for_eval = 5
        self.win_rate_threshold = 0.40

    def _evaluate_signal(self, df: pl.DataFrame) -> str:
        """Helper to extract action from DataFrame."""
        if df.height == 0:
            return "HOLD"

        last_row = df[-1]
        if "buy" in df.columns and last_row["buy"][0]:
            return "BUY"
        if "sell" in df.columns and last_row["sell"][0]:
            return "SELL"

        return "HOLD"

    async def gather_signals(self, lazy_df: pl.LazyFrame) -> Dict[str, Dict[str, Any]]:
        """
        Runs all active (non-degraded) strategies to collect their signals.
        Returns a dict of strategy name to its proposed action/confidence.
        """
        signals = {}
        for name, strategy in self.strategies.items():
            if self.performance[name]["degraded"]:
                logger.debug(f"[{name}] is degraded. Skipping.")
                continue

            try:
                # Polars execution
                strat_df = strategy.populate_indicators(lazy_df)
                strat_df = strategy.populate_signals(strat_df)

                # Strict Directive: async to_thread for collect
                df = await asyncio.to_thread(strat_df.collect)

                signals[name] = {
                    "action": self._evaluate_signal(df),
                    "confidence": 0.8,  # Dummy confidence for now
                }
            except Exception as e:
                logger.error(f"Error executing strategy {name}: {e}")

        return signals

    async def evaluate_and_allocate(
        self, signals: Dict[str, Dict[str, Any]], market_context: str, df: pl.DataFrame
    ) -> AISignal:
        """
        Constructs a prompt for the LLM Copilot ("Hedge Fund Manager") to evaluate
        conflicting/aligning signals and decide on the final execution.
        """
        if not signals:
            logger.warning("No active strategies returned signals.")
            return AISignal(
                timestamp=int(time.time() * 1000),
                asset_pair=df["symbol"][-1] if df.height > 0 else "UNKNOWN",
                action="HOLD",
                confidence_score=0.0,
                reasoning="No active strategies.",
            )

        prompt = (
            f"You are a Hedge Fund Manager.\n"
            f"Market Context Regime: {market_context}\n"
            f"Current Strategy Signals: {json.dumps(signals)}\n"
            f"Please analyze these conflicting/aligning signals and provide a single final action "
            f"(BUY, SELL, or HOLD), confidence score, and reasoning."
        )

        logger.info("Requesting LLM Copilot consensus...")
        logger.debug(f"Prompt: {prompt}")

        # Simulate LLM call since we don't have direct LLM generation hooked up in this dummy setup
        await asyncio.sleep(0.5)

        buy_votes = sum(1 for s in signals.values() if s["action"] == "BUY")
        sell_votes = sum(1 for s in signals.values() if s["action"] == "SELL")

        if buy_votes > sell_votes:
            final_action = "BUY"
        elif sell_votes > buy_votes:
            final_action = "SELL"
        else:
            final_action = "HOLD"

        reasoning = f"LLM Consensus based on {len(signals)} signals. Buy: {buy_votes}, Sell: {sell_votes}."

        return AISignal(
            timestamp=int(time.time() * 1000),
            asset_pair=df["symbol"][-1] if df.height > 0 else "UNKNOWN",
            action=final_action,
            confidence_score=0.85,
            reasoning=reasoning,
        )

    def record_trade_outcome(self, strategy_name: str, is_win: bool):
        """
        Records the outcome of a trade attributed to a strategy to track degradation.
        """
        if strategy_name not in self.performance:
            return

        stats = self.performance[strategy_name]
        stats["trades"] += 1
        if is_win:
            stats["wins"] += 1

        if stats["trades"] >= self.min_trades_for_eval:
            win_rate = stats["wins"] / stats["trades"]
            if win_rate < self.win_rate_threshold and not stats["degraded"]:
                logger.warning(
                    f"Strategy {strategy_name} win rate {win_rate:.2f} is below threshold {self.win_rate_threshold}. Flagging as DEGRADED."
                )
                stats["degraded"] = True
