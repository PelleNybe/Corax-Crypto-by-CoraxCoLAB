"""
Profitability Calculator Module.
Provides high-performance cost calculations for arbitrage opportunities, including
CEX trading fees, slippage estimations, and on-chain bridge/gas costs.
Designed for both scalar operations and vectorised Polars pipelines.
"""

import polars as pl
from typing import Dict, Any


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
        orderbook_buy: Dict[str, Any],
        orderbook_sell: Dict[str, Any],
        trade_amount_base: float,
        price_buy: float,
        price_sell: float,
    ) -> float:
        """
        Estimates slippage in USD based on orderbook top level depth.
        Penalizes the spread if the trade size exceeds the top-of-book volume.

        Args:
            orderbook_buy (Dict[str, Any]): The orderbook for the buy exchange.
            orderbook_sell (Dict[str, Any]): The orderbook for the sell exchange.
            trade_amount_base (float): The amount of base asset to trade.
            price_buy (float): The top ask price on the buy exchange.
            price_sell (float): The top bid price on the sell exchange.

        Returns:
            float: Estimated slippage cost in USD.
        """
        buy_top_amt = orderbook_buy["asks"][0][1] if orderbook_buy["asks"] else 0.0
        sell_top_amt = orderbook_sell["bids"][0][1] if orderbook_sell["bids"] else 0.0

        slippage_penalty = 0.0

        # 0.5% severe slippage for amounts exceeding top-of-book depth
        penalty_rate = 0.005

        if trade_amount_base > buy_top_amt:
            slippage_penalty += (
                (trade_amount_base - buy_top_amt) * price_buy * penalty_rate
            )

        if trade_amount_base > sell_top_amt:
            slippage_penalty += (
                (trade_amount_base - sell_top_amt) * price_sell * penalty_rate
            )

        # Base slippage of 1 bps for all trades
        base_slippage = (trade_amount_base * price_buy) * 0.0001

        return slippage_penalty + base_slippage

    @classmethod
    def calculate_net_profitability(
        cls,
        symbol: str,
        exchange_buy: str,
        exchange_sell: str,
        ask_price: float,
        bid_price: float,
        trade_amount_base: float,
        orderbook_buy: Dict[str, Any],
        orderbook_sell: Dict[str, Any],
    ) -> Dict[str, float]:
        """
        Calculates net profitability for a given arbitrage opportunity.

        Args:
            symbol (str): The trading pair symbol.
            exchange_buy (str): The exchange to buy from.
            exchange_sell (str): The exchange to sell to.
            ask_price (float): The lowest ask price on the buy exchange.
            bid_price (float): The highest bid price on the sell exchange.
            trade_amount_base (float): The base asset amount to trade.
            orderbook_buy (Dict[str, Any]): The L2 orderbook of the buy exchange.
            orderbook_sell (Dict[str, Any]): The L2 orderbook of the sell exchange.

        Returns:
            Dict[str, float]: A dictionary containing gross and net margins and costs.
        """
        trade_size_usd = trade_amount_base * ask_price
        gross_profit_usd = (bid_price - ask_price) * trade_amount_base
        gross_margin_pct = (
            (gross_profit_usd / trade_size_usd) * 100 if trade_size_usd > 0 else 0.0
        )

        cex_fees_usd = cls.calculate_fees(exchange_buy, exchange_sell, trade_size_usd)
        slippage_usd = cls.estimate_slippage(
            orderbook_buy, orderbook_sell, trade_amount_base, ask_price, bid_price
        )
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
        ask_col: str,
        bid_col: str,
        exchange_buy: str,
        exchange_sell: str,
        trade_size_usd: float = 1000.0,
    ) -> pl.Expr:
        """
        Generates a Polars Expression to calculate net margin across an entire DataFrame.
        This enables blazingly fast vectorised backtesting and scanning.

        Args:
            ask_col (str): Column name for the ask price.
            bid_col (str): Column name for the bid price.
            exchange_buy (str): Exchange identifier for the buy leg.
            exchange_sell (str): Exchange identifier for the sell leg.
            trade_size_usd (float): Assumed trade size in USD for calculating flat costs.

        Returns:
            pl.Expr: A Polars expression evaluating to the net margin percentage.
        """
        fee_buy = cls.CEX_FEES.get(exchange_buy, cls.CEX_FEES["default"])["taker"]
        fee_sell = cls.CEX_FEES.get(exchange_sell, cls.CEX_FEES["default"])["taker"]
        total_fee_pct = fee_buy + fee_sell

        base_slippage_pct = 0.0001
        on_chain_pct = (
            cls.ON_CHAIN_GAS_FEE_USD / trade_size_usd if trade_size_usd > 0 else 0.0
        )

        gross_margin = (pl.col(bid_col) - pl.col(ask_col)) / pl.col(ask_col)
        net_margin = gross_margin - total_fee_pct - base_slippage_pct - on_chain_pct

        return net_margin * 100.0
