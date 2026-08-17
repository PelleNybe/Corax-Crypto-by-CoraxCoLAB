from abc import ABC, abstractmethod
import polars as pl
import asyncio
from loguru import logger

try:
    import torch  # noqa: F401
except ImportError:
    logger.warning(
        "torch is not installed; HardwareEdgeBackend may not be fully functional."
    )


class BaseInferenceBackend(ABC):
    """Base interface for all AI inference backends."""

    @abstractmethod
    async def fast_inference(self, df: pl.DataFrame) -> dict:
        """Execute high-speed local inference."""
        raise NotImplementedError


class StandardCPUBackend(BaseInferenceBackend):
    """
    Default fallback backend utilizing standard CPU operations.
    Guarantees hardware agnosticism and execution on any standard Linux distro.
    """

    async def fast_inference(self, df: pl.DataFrame) -> dict:
        # Use actual Polars calculation for inference instead of simulation
        if df.height < 10:
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "fast_reason": "Insufficient data",
            }

        def calculate_signals():
            # Example calculation: basic momentum
            prices = df["price"]
            momentum = (prices[-1] - prices[0]) / prices[0]

            if momentum > 0.001:
                return {
                    "action": "BUY",
                    "confidence": min(0.5 + momentum * 100, 1.0),
                    "fast_reason": "CPU: Positive Momentum",
                }
            elif momentum < -0.001:
                return {
                    "action": "SELL",
                    "confidence": min(0.5 + abs(momentum) * 100, 1.0),
                    "fast_reason": "CPU: Negative Momentum",
                }
            return {"action": "HOLD", "confidence": 0.0, "fast_reason": "CPU: Ranging"}

        # Run CPU-bound calculation in a separate thread to avoid blocking event loop
        return await asyncio.to_thread(calculate_signals)


class HardwareEdgeBackend(BaseInferenceBackend):
    """
    High-performance backend for specialized Edge AI hardware using PyTorch.
    """

    def __init__(self):
        import torch
        import torch.nn as nn

        # Determine device
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Simple predictive model expecting OHLCV (5 features)
        self.model = nn.Sequential(
            nn.Linear(5, 10),
            nn.ReLU(),
            nn.Linear(10, 3),  # output: [buy_score, hold_score, sell_score]
            nn.Softmax(dim=1),
        ).to(self.device)
        self.model.eval()

    async def fast_inference(self, df: pl.DataFrame) -> dict:
        if df.height == 0:
            return {"action": "HOLD", "confidence": 0.0, "fast_reason": "No data"}

        def run_torch_inference():
            import torch

            # Extract last row OHLCV assuming these columns exist
            # fallback to zeros if missing
            row = df[-1]
            features = []
            for col in ["open", "high", "low", "close", "volume"]:
                if col in row.columns:
                    features.append(float(row[col][0]))
                elif col == "price":  # fallback mapping
                    features.append(float(row["price"][0]))
                else:
                    features.append(0.0)

            while len(features) < 5:
                features.append(0.0)

            tensor_in = torch.tensor([features], dtype=torch.float32).to(self.device)
            with torch.no_grad():
                out = self.model(tensor_in)
                probs = out[0].tolist()

            buy_prob, hold_prob, sell_prob = probs

            if buy_prob > hold_prob and buy_prob > sell_prob:
                return {
                    "action": "BUY",
                    "confidence": buy_prob,
                    "fast_reason": "NPU Tensor: Buy probability dominates",
                }
            elif sell_prob > hold_prob and sell_prob > buy_prob:
                return {
                    "action": "SELL",
                    "confidence": sell_prob,
                    "fast_reason": "NPU Tensor: Sell probability dominates",
                }
            else:
                return {
                    "action": "HOLD",
                    "confidence": hold_prob,
                    "fast_reason": "NPU Tensor: No clear direction",
                }

        # Must wrap CPU/GPU bound calculations
        return await asyncio.to_thread(run_torch_inference)
