from pydantic import BaseModel, Field
from typing import Literal


class AISignal(BaseModel):
    timestamp: int = Field(
        description="Timestamp of the signal generation in milliseconds"
    )
    asset_pair: str = Field(description="The trading pair, e.g., BTC/USDT")
    action: Literal["BUY", "SELL", "HOLD"] = Field(
        description="Recommended trading action"
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0"
    )
    reasoning: str = Field(description="Brief explanation of the AI's reasoning")
