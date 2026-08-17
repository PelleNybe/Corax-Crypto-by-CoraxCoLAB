from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class ExecutionType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    TWAP = "twap"
    VWAP = "vwap"
    ICEBERG = "iceberg"


class OrderContext(BaseModel):
    symbol: str = Field(..., description="The trading pair symbol, e.g., 'BTC/USDT'")
    side: str = Field(..., description="The side of the order, 'buy' or 'sell'")
    order_type: str = Field(
        ..., description="The type of order, e.g., 'market' or 'limit'"
    )
    amount: float = Field(..., description="The amount to trade")
    current_price: Optional[float] = Field(
        None, description="The current price of the asset"
    )
    execution_algo: Optional[ExecutionType] = Field(
        None, description="Algo type if not instant"
    )
    algo_params: Optional[dict] = Field(
        None, description="Parameters for the execution algo"
    )


class GridLine(BaseModel):
    price: float = Field(..., description="Target execution price")
    side: str = Field(..., description="buy or sell")
    amount: float = Field(..., description="Size of order per line")
    order_id: Optional[str] = Field(None, description="Exchange order ID if active")
    is_active: bool = Field(False, description="Is order currently on the book")


class GridState(BaseModel):
    symbol: str
    lines: list[GridLine] = []
