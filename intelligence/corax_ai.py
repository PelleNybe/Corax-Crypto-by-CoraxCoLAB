import asyncio
import time
import polars as pl
from loguru import logger
from schemas.signals import AISignal
from intelligence.backends import (
    StandardCPUBackend,
    HardwareEdgeBackend,
    BaseInferenceBackend,
)
from core.config import settings


class CoraxAIEngine:
    """
    CoraxAIEngine handles AI-driven market analysis.
    Dynamically routes fast inference to the appropriate hardware backend.
    """

    def __init__(self):
        backend_type = settings.CORAX_HARDWARE_BACKEND.upper()

        if backend_type == "EDGE_NPU":
            logger.info("Initializing HardwareEdgeBackend (NPU Accelerated).")
            self.fast_backend: BaseInferenceBackend = HardwareEdgeBackend()
        else:
            logger.info("Initializing StandardCPUBackend (Hardware Agnostic).")
            self.fast_backend: BaseInferenceBackend = StandardCPUBackend()

    async def _deep_llm_inference(self, df: pl.DataFrame, regime: str) -> dict:
        await asyncio.sleep(0.05)
        if regime == "RANGING":
            return {
                "action": "HOLD",
                "confidence": 0.90,
                "deep_reason": "LLM: Market is ranging. Avoiding chop.",
            }
        elif regime == "VOLATILE_CRASH":
            return {
                "action": "SELL",
                "confidence": 0.95,
                "deep_reason": "LLM: Volatility spike detected. Exiting risk.",
            }
        return {
            "action": "BUY",
            "confidence": 0.88,
            "deep_reason": f"LLM: Order flow aligns with {regime} macro.",
        }

    async def analyze_market_state(
        self, df: pl.DataFrame, regime: str = "RANGING"
    ) -> AISignal:
        # df is already collected
        if df.height == 0:
            return AISignal(
                timestamp=int(time.time() * 1000),
                asset_pair="UNKNOWN",
                action="HOLD",
                confidence_score=0.0,
                reasoning="No data available",
            )

        symbol = df["symbol"][-1]

        fast_task = asyncio.create_task(self.fast_backend.fast_inference(df))
        deep_task = asyncio.create_task(self._deep_llm_inference(df, regime))

        fast_result, deep_result = await asyncio.gather(fast_task, deep_task)

        final_action = deep_result["action"]

        if regime == "RANGING":
            final_confidence = deep_result["confidence"]
        else:
            final_confidence = (
                fast_result["confidence"] + deep_result["confidence"]
            ) / 2.0

        reasoning = (
            f"[{regime}] {fast_result['fast_reason']} | {deep_result['deep_reason']}"
        )

        return AISignal(
            timestamp=int(time.time() * 1000),
            asset_pair=symbol,
            action=final_action,
            confidence_score=final_confidence,
            reasoning=reasoning,
        )
