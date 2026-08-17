from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal
import re


class AISignal(BaseModel):
    timestamp: int = Field(
        description="Timestamp of the signal generation in milliseconds", gt=0
    )
    asset_pair: str = Field(description="The trading pair, e.g., BTC/USDT")
    action: Literal["BUY", "SELL", "HOLD"] = Field(
        description="Recommended trading action"
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0"
    )
    reasoning: str = Field(description="Brief explanation of the AI's reasoning")

    @field_validator("asset_pair")
    @classmethod
    def validate_asset_pair(cls, v: str) -> str:
        if v != "UNKNOWN" and not re.match(r"^[A-Z0-9]+/[A-Z0-9]+$", v):
            raise ValueError("Asset pair must be in the format BASE/QUOTE or UNKNOWN")
        return v

    @model_validator(mode="after")
    def validate_action_confidence(self) -> "AISignal":
        if self.action in ("BUY", "SELL") and self.confidence_score == 0.0:
            raise ValueError("Confidence score must be > 0.0 for BUY/SELL actions")
        return self
