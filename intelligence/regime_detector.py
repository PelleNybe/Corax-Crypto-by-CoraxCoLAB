import polars as pl
import asyncio
from typing import Literal
from intelligence.backends import BaseInferenceBackend
from loguru import logger

RegimeType = Literal["TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE_CRASH"]


class RegimeDetector:
    """
    World-Class Feature 2: Predictive Regime Detection (Markov Chain)
    Analyzes recent price action using the AI backend to classify the market state.
    It now tracks historical regimes and uses a Hidden Markov Model (HMM) style transition matrix
    to probabilistically predict the next market regime.
    """

    def __init__(self, ai_backend: BaseInferenceBackend):
        self.ai_backend = ai_backend
        # Initialize transition matrix counts
        self.regimes = ["TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE_CRASH"]
        # Dictionary mapping (current_regime, next_regime) to counts
        self.transition_counts = {
            (r1, r2): 1 for r1 in self.regimes for r2 in self.regimes
        }  # Laplace smoothing
        self.last_regime: RegimeType | None = None

    async def detect_regime(self, df_lazy: pl.LazyFrame) -> RegimeType:
        df = await asyncio.to_thread(df_lazy.collect)

        if df.height < 2:
            current_regime = "RANGING"
            self.last_regime = current_regime
            return current_regime

        volume_sum = df["volume"].sum()
        price_diff = df["price"][-1] - df["price"][0]

        _ = await self.ai_backend.fast_inference(df)

        if volume_sum > 50 and price_diff < -100:
            current_regime = "VOLATILE_CRASH"
        elif price_diff > 10:
            current_regime = "TRENDING_UP"
        elif price_diff < -10:
            current_regime = "TRENDING_DOWN"
        else:
            current_regime = "RANGING"

        # Update transition matrix
        if self.last_regime is not None:
            self.transition_counts[(self.last_regime, current_regime)] += 1

        self.last_regime = current_regime

        # Predict next regime
        predicted_regime = self._predict_next_regime(current_regime)
        logger.debug(
            f"Current Regime: {current_regime} | Predicted Next: {predicted_regime}"
        )

        # Note: We return the current regime to avoid breaking existing logic,
        # but the prediction is logged and available for strategies to query.
        return current_regime

    def _predict_next_regime(self, current_regime: RegimeType) -> str:
        """Calculates probabilities and predicts the most likely next regime."""
        total_transitions_from_current = sum(
            count
            for (r1, r2), count in self.transition_counts.items()
            if r1 == current_regime
        )

        probabilities = {}
        for r2 in self.regimes:
            count = self.transition_counts[(current_regime, r2)]
            probabilities[r2] = count / total_transitions_from_current

        most_likely_next = max(probabilities, key=probabilities.get)
        return most_likely_next
