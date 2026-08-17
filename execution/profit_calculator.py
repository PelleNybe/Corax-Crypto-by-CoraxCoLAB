"""
Profitability Calculator Module.
Provides high-performance cost calculations for arbitrage opportunities, including
CEX trading fees, slippage estimations, and on-chain bridge/gas costs.
Designed for both scalar operations and vectorised Polars pipelines.
"""

import polars as pl
from typing import Dict, Any
from pydantic import BaseModel


class ProfitConfig(BaseModel):
    penalty_rate: float = 0.005
    base_slippage_pct: float = 0.0001
    trade_size_usd_fallback: float = 1000.0


class MarginExprConfig(BaseModel):
    ask_col: str
    bid_col: str
    exchange_buy: str
    exchange_sell: str
    trade_size_usd: float | None = None
    config: ProfitConfig = ProfitConfig()


class ProfitabilityRequest(BaseModel):
    symbol: str
    exchange_buy: str
    exchange_sell: str
    ask_price: float
    bid_price: float
    trade_amount_base: float
    orderbook_buy: Dict[str, Any]
    orderbook_sell: Dict[str, Any]


class ProfitCalculator:
    """
    Calculates net profitability for arbitrage trades.
    Includes CEX fees, estimated slippage from orderbook depth, and flat on-chain costs.
    """

    CEX_FEES: Dict[str, Dict[str, float]] = {
        "binance": {"maker": 0.001, "taker": 0.001},
        "bybit": {"maker": 0.001, "taker": 0.001},
        "okx": {"maker": 0.0008, "taker": 0.001},
        "bitget": {"maker": 0.001, "taker": 0.001},
        "default": {"maker": 0.001, "taker": 0.001},
    }

    ON_CHAIN_GAS_FEE_USD: float = 1.50

    @classmethod
    def calculate_fees(
        cls, exchange_buy: str, exchange_sell: str, trade_size_usd: float
    ) -> float:
        """
        Calculates total CEX taker fees for both legs of the arbitrage.

        Args:
            exchange_buy (str): Exchange identifier for the buy leg.
            exchange_sell (str): Exchange identifier for the sell leg.
            trade_size_usd (float): The total trade size in USD.

        Returns:
            float: Total taker fees in USD.
        """
        fee_buy_pct = cls.CEX_FEES.get(exchange_buy, cls.CEX_FEES["default"])["taker"]
        fee_sell_pct = cls.CEX_FEES.get(exchange_sell, cls.CEX_FEES["default"])["taker"]

        return trade_size_usd * (fee_buy_pct + fee_sell_pct)

    @classmethod
    def estimate_slippage(
        cls,
        request: ProfitabilityRequest,
        config: ProfitConfig = None,
    ) -> float:
        """
        Estimates slippage in USD based on orderbook top level depth.
        Penalizes the spread if the trade size exceeds the top-of-book volume.

        Args:
            request (ProfitabilityRequest): Request object with orderbooks and trade details.
            config (ProfitConfig): Configuration for slippage penalties.

        Returns:
            float: Estimated slippage cost in USD.
        """
        config = config or ProfitConfig()
        buy_top_amt = (
            request.orderbook_buy["asks"][0][1]
            if request.orderbook_buy["asks"]
            else 0.0
        )
        sell_top_amt = (
            request.orderbook_sell["bids"][0][1]
            if request.orderbook_sell["bids"]
            else 0.0
        )

        slippage_penalty = 0.0

        if request.trade_amount_base > buy_top_amt:
            slippage_penalty += (
                (request.trade_amount_base - buy_top_amt)
                * request.ask_price
                * config.penalty_rate
            )

        if request.trade_amount_base > sell_top_amt:
            slippage_penalty += (
                (request.trade_amount_base - sell_top_amt)
                * request.bid_price
                * config.penalty_rate
            )

        base_slippage = (
            request.trade_amount_base * request.ask_price
        ) * config.base_slippage_pct

        return slippage_penalty + base_slippage

    @classmethod
    def calculate_net_profitability(
        cls,
        request: ProfitabilityRequest,
        config: ProfitConfig = None,
    ) -> Dict[str, float]:
        """
        Calculates net profitability for a given arbitrage opportunity.

        Args:
            request (ProfitabilityRequest): A request object containing all necessary parameters.
            config (ProfitConfig): Configuration for slippage penalties.

        Returns:
            Dict[str, float]: A dictionary containing gross and net margins and costs.
        """
        config = config or ProfitConfig()
        trade_size_usd = request.trade_amount_base * request.ask_price
        gross_profit_usd = (
            request.bid_price - request.ask_price
        ) * request.trade_amount_base
        gross_margin_pct = (
            (gross_profit_usd / trade_size_usd) * 100 if trade_size_usd > 0 else 0.0
        )

        cex_fees_usd = cls.calculate_fees(
            request.exchange_buy, request.exchange_sell, trade_size_usd
        )
        slippage_usd = cls.estimate_slippage(request, config=config)
        on_chain_fees_usd = cls.ON_CHAIN_GAS_FEE_USD

        net_profit_usd = (
            gross_profit_usd - cex_fees_usd - slippage_usd - on_chain_fees_usd
        )
        net_margin_pct = (
            (net_profit_usd / trade_size_usd) * 100 if trade_size_usd > 0 else 0.0
        )

        return {
            "gross_margin_pct": gross_margin_pct,
            "cex_fees_usd": cex_fees_usd,
            "slippage_usd": slippage_usd,
            "on_chain_fees_usd": on_chain_fees_usd,
            "net_profit_usd": net_profit_usd,
            "net_margin_pct": net_margin_pct,
        }

    @classmethod
    def get_net_margin_expr(
        cls,
        expr_config: MarginExprConfig,
    ) -> pl.Expr:
        """
        Generates a Polars Expression to calculate net margin across an entire DataFrame.
        This enables blazingly fast vectorised backtesting and scanning.

        Args:
            expr_config (MarginExprConfig): Configuration for generating the net margin expression.

        Returns:
            pl.Expr: A Polars expression evaluating to the net margin percentage.
        """
        config = expr_config.config
        trade_size_usd = (
            expr_config.trade_size_usd
            if expr_config.trade_size_usd is not None
            else config.trade_size_usd_fallback
        )

        fee_buy = cls.CEX_FEES.get(expr_config.exchange_buy, cls.CEX_FEES["default"])[
            "taker"
        ]
        fee_sell = cls.CEX_FEES.get(expr_config.exchange_sell, cls.CEX_FEES["default"])[
            "taker"
        ]
        total_fee_pct = fee_buy + fee_sell

        on_chain_pct = (
            cls.ON_CHAIN_GAS_FEE_USD / trade_size_usd if trade_size_usd > 0 else 0.0
        )

        gross_margin = (
            pl.col(expr_config.bid_col) - pl.col(expr_config.ask_col)
        ) / pl.col(expr_config.ask_col)
        net_margin = (
            gross_margin - total_fee_pct - config.base_slippage_pct - on_chain_pct
        )

        return net_margin * 100.0
