import polars as pl
import asyncio
from typing import Literal
from intelligence.backends import BaseInferenceBackend

RegimeType = Literal["TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE_CRASH"]


class RegimeDetector:
    """
    Market Regime Detector.
    Analyzes recent price action using the AI backend to classify the market state.
    """

    def __init__(self, ai_backend: BaseInferenceBackend):
        self.ai_backend = ai_backend

    async def detect_regime(self, df_lazy: pl.LazyFrame) -> RegimeType:
        df = await asyncio.to_thread(df_lazy.collect)

        if df.height < 2:
            return "RANGING"

        volume_sum = df["volume"].sum()
        price_diff = df["price"][-1] - df["price"][0]

        _ = await self.ai_backend.fast_inference(df)

        if volume_sum > 50 and price_diff < -100:
            regime = "VOLATILE_CRASH"
        elif price_diff > 10:
            regime = "TRENDING_UP"
        elif price_diff < -10:
            regime = "TRENDING_DOWN"
        else:
            regime = "RANGING"

        return regime
