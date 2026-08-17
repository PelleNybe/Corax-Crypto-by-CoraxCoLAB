from pydantic import BaseModel, Field
from typing import Optional, Literal


class TWAPConfig(BaseModel):
    duration_minutes: int = Field(
        ..., gt=0, description="Total duration of the TWAP execution in minutes"
    )
    slices: int = Field(
        ..., gt=1, description="Number of slices to break the total amount into"
    )
    randomize_delay_pct: float = Field(
        default=0.2,
        ge=0.0,
        le=0.5,
        description="Randomize execution delays up to X percent to prevent pattern detection",
    )


class IcebergConfig(BaseModel):
    visible_size: float = Field(
        ...,
        gt=0.0,
        description="The size of the order to show on the public order book",
    )
    price_variance_pct: float = Field(
        default=0.001,
        description="Allowed variance from original limit price when refreshing the tip",
    )


class AlgoOrderRequest(BaseModel):
    algo_type: Literal["TWAP", "ICEBERG"] = Field(
        ..., description="The institutional algorithm to execute"
    )
    symbol: str = Field(..., description="Trading pair, e.g., 'BTC/USDT'")
    side: Literal["buy", "sell"] = Field(..., description="Order direction")
    total_amount: float = Field(
        ..., gt=0.0, description="Total amount to execute over the life of the algo"
    )
    limit_price: Optional[float] = Field(
        None, description="Limit price. If None, slices use market orders."
    )

    twap_config: Optional[TWAPConfig] = None
    iceberg_config: Optional[IcebergConfig] = None
