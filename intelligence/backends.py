from abc import ABC, abstractmethod
import polars as pl
import asyncio


class BaseInferenceBackend(ABC):
    """Base interface for all AI inference backends."""

    @abstractmethod
    async def fast_inference(self, df: pl.DataFrame) -> dict:
        """Execute high-speed local inference."""
        pass


class StandardCPUBackend(BaseInferenceBackend):
    """
    Default fallback backend utilizing standard CPU operations.
    Guarantees hardware agnosticism and execution on any standard Linux distro.
    """

    async def fast_inference(self, df: pl.DataFrame) -> dict:
        # Simulate standard CPU-bound mathematical calculations (e.g., standard Polars analytics)
        await asyncio.sleep(0.005)  # Slightly slower than Edge AI
        return {
            "action": "BUY",
            "confidence": 0.75,
            "fast_reason": "CPU: Moving Average Crossover",
        }


class HardwareEdgeBackend(BaseInferenceBackend):
    """
    High-performance backend for specialized Edge AI hardware (e.g., Hailo NPU).
    Injected dynamically when hardware is detected.
    """

    async def fast_inference(self, df: pl.DataFrame) -> dict:
        # Simulate ultra-fast tensor operations on an NPU
        await asyncio.sleep(0.001)  # Ultra low latency
        return {
            "action": "BUY",
            "confidence": 0.95,
            "fast_reason": "NPU: Micro-structure momentum detected",
        }
