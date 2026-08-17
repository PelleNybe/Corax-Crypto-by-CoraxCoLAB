from execution.profit_calculator import (
    ProfitCalculator,
    ProfitabilityRequest,
    MarginExprConfig,
)
import math
import polars as pl
from polars.testing import assert_frame_equal


def test_calculate_fees_known_exchanges():
    # Binance taker fee: 0.001
    # Bybit taker fee: 0.001
    # Total fee: 0.002
    fee = ProfitCalculator.calculate_fees("binance", "bybit", 1000.0)
    assert math.isclose(fee, 1000.0 * (0.001 + 0.001))


def test_calculate_fees_unknown_exchanges():
    # Unknown exchanges should fallback to 'default'
    # Default taker fee: 0.001
    fee = ProfitCalculator.calculate_fees("unknown1", "unknown2", 2000.0)
    assert math.isclose(fee, 2000.0 * (0.001 + 0.001))


def test_calculate_fees_mixed_exchanges():
    # OKX taker fee: 0.001
    # Unknown fallback default taker fee: 0.001
    fee = ProfitCalculator.calculate_fees("okx", "unknown", 500.0)
    assert math.isclose(fee, 500.0 * (0.001 + 0.001))


def test_calculate_fees_zero_trade_size():
    fee = ProfitCalculator.calculate_fees("binance", "bybit", 0.0)
    assert math.isclose(fee, 0.0)


def test_calculate_fees_negative_trade_size():
    # While typically not used, the math should still hold
    fee = ProfitCalculator.calculate_fees("binance", "bybit", -100.0)
    assert math.isclose(fee, -100.0 * (0.001 + 0.001))


def test_get_net_margin_expr_standard_case():
    # Setup
    df = pl.DataFrame({"ask": [100.0, 100.0], "bid": [105.0, 102.0]})

    expr = ProfitCalculator.get_net_margin_expr(
        MarginExprConfig(
            ask_col="ask",
            bid_col="bid",
            exchange_buy="binance",
            exchange_sell="bybit",
            trade_size_usd=1000.0,
        )
    )

    result = df.with_columns(expr.alias("net_margin"))

    expected = pl.DataFrame(
        {"ask": [100.0, 100.0], "bid": [105.0, 102.0], "net_margin": [4.64, 1.64]}
    )

    assert_frame_equal(result, expected)


def test_get_net_margin_expr_zero_trade_size():
    # Setup
    df = pl.DataFrame({"ask": [100.0], "bid": [105.0]})

    expr = ProfitCalculator.get_net_margin_expr(
        MarginExprConfig(
            ask_col="ask",
            bid_col="bid",
            exchange_buy="binance",
            exchange_sell="bybit",
            trade_size_usd=0.0,
        )
    )

    result = df.with_columns(expr.alias("net_margin"))

    expected = pl.DataFrame({"ask": [100.0], "bid": [105.0], "net_margin": [4.79]})

    assert_frame_equal(result, expected)


def test_get_net_margin_expr_fallback_exchange():
    # Setup
    df = pl.DataFrame({"ask": [100.0], "bid": [105.0]})

    expr = ProfitCalculator.get_net_margin_expr(
        MarginExprConfig(
            ask_col="ask",
            bid_col="bid",
            exchange_buy="unknown",
            exchange_sell="okx",
            trade_size_usd=1500.0,
        )
    )

    result = df.with_columns(expr.alias("net_margin"))

    expected = pl.DataFrame({"ask": [100.0], "bid": [105.0], "net_margin": [4.69]})

    assert_frame_equal(result, expected)


def test_estimate_slippage_no_penalty():
    request = ProfitabilityRequest(
        symbol="BTC/USDT",
        exchange_buy="binance",
        exchange_sell="bybit",
        ask_price=100.0,
        bid_price=102.0,
        trade_amount_base=5.0,
        orderbook_buy={"asks": [[100.0, 10.0]]},
        orderbook_sell={"bids": [[102.0, 10.0]]},
    )

    slippage = ProfitCalculator.estimate_slippage(request)

    # base_slippage = 5.0 * 100.0 * 0.0001 = 0.05
    # slippage_penalty = 0.0
    assert math.isclose(slippage, 0.05)


def test_estimate_slippage_penalty_buy_side():
    request = ProfitabilityRequest(
        symbol="BTC/USDT",
        exchange_buy="binance",
        exchange_sell="bybit",
        ask_price=100.0,
        bid_price=102.0,
        trade_amount_base=5.0,
        orderbook_buy={"asks": [[100.0, 4.0]]},
        orderbook_sell={"bids": [[102.0, 10.0]]},
    )

    slippage = ProfitCalculator.estimate_slippage(request)

    # base_slippage = 5.0 * 100.0 * 0.0001 = 0.05
    # penalty_buy = (5.0 - 4.0) * 100.0 * 0.005 = 0.5
    # penalty_sell = 0.0
    assert math.isclose(slippage, 0.55)


def test_estimate_slippage_penalty_sell_side():
    request = ProfitabilityRequest(
        symbol="BTC/USDT",
        exchange_buy="binance",
        exchange_sell="bybit",
        ask_price=100.0,
        bid_price=102.0,
        trade_amount_base=5.0,
        orderbook_buy={"asks": [[100.0, 10.0]]},
        orderbook_sell={"bids": [[102.0, 4.0]]},
    )

    slippage = ProfitCalculator.estimate_slippage(request)

    # base_slippage = 5.0 * 100.0 * 0.0001 = 0.05
    # penalty_buy = 0.0
    # penalty_sell = (5.0 - 4.0) * 102.0 * 0.005 = 0.51
    assert math.isclose(slippage, 0.56)


def test_estimate_slippage_penalty_both_sides():
    request = ProfitabilityRequest(
        symbol="BTC/USDT",
        exchange_buy="binance",
        exchange_sell="bybit",
        ask_price=100.0,
        bid_price=102.0,
        trade_amount_base=5.0,
        orderbook_buy={"asks": [[100.0, 2.0]]},
        orderbook_sell={"bids": [[102.0, 3.0]]},
    )

    slippage = ProfitCalculator.estimate_slippage(request)

    # base_slippage = 5.0 * 100.0 * 0.0001 = 0.05
    # penalty_buy = (5.0 - 2.0) * 100.0 * 0.005 = 1.5
    # penalty_sell = (5.0 - 3.0) * 102.0 * 0.005 = 1.02
    assert math.isclose(slippage, 2.57)


def test_estimate_slippage_empty_orderbooks():
    request = ProfitabilityRequest(
        symbol="BTC/USDT",
        exchange_buy="binance",
        exchange_sell="bybit",
        ask_price=100.0,
        bid_price=102.0,
        trade_amount_base=5.0,
        orderbook_buy={"asks": []},
        orderbook_sell={"bids": []},
    )

    slippage = ProfitCalculator.estimate_slippage(request)

    # base_slippage = 5.0 * 100.0 * 0.0001 = 0.05
    # top_amt = 0.0 for both
    # penalty_buy = 5.0 * 100.0 * 0.005 = 2.5
    # penalty_sell = 5.0 * 102.0 * 0.005 = 2.55
    assert math.isclose(slippage, 5.10)


def test_calculate_net_profitability_standard():
    request = ProfitabilityRequest(
        symbol="BTC/USDT",
        exchange_buy="binance",
        exchange_sell="bybit",
        ask_price=100.0,
        bid_price=105.0,
        trade_amount_base=5.0,
        orderbook_buy={"asks": [[100.0, 10.0]]},
        orderbook_sell={"bids": [[102.0, 10.0]]},
    )

    result = ProfitCalculator.calculate_net_profitability(request)

    gross_margin_pct = (25.0 / 500.0) * 100  # 5.0

    cex_fees_usd = 500.0 * (0.001 + 0.001)  # 1.0

    # base slippage = 5.0 * 100.0 * 0.0001 = 0.05
    # penalty = 0.0
    slippage_usd = 0.05
    on_chain_fees_usd = 1.5

    net_profit_usd = 25.0 - 1.0 - 0.05 - 1.5  # 22.45
    net_margin_pct = (22.45 / 500.0) * 100  # 4.49

    assert math.isclose(result["gross_margin_pct"], gross_margin_pct)
    assert math.isclose(result["cex_fees_usd"], cex_fees_usd)
    assert math.isclose(result["slippage_usd"], slippage_usd)
    assert math.isclose(result["on_chain_fees_usd"], on_chain_fees_usd)
    assert math.isclose(result["net_profit_usd"], net_profit_usd)
    assert math.isclose(result["net_margin_pct"], net_margin_pct)


def test_calculate_net_profitability_zero_trade_size():
    request = ProfitabilityRequest(
        symbol="BTC/USDT",
        exchange_buy="binance",
        exchange_sell="bybit",
        ask_price=100.0,
        bid_price=105.0,
        trade_amount_base=0.0,
        orderbook_buy={"asks": [[100.0, 10.0]]},
        orderbook_sell={"bids": [[102.0, 10.0]]},
    )

    result = ProfitCalculator.calculate_net_profitability(request)

    assert math.isclose(result["gross_margin_pct"], 0.0)
    assert math.isclose(result["cex_fees_usd"], 0.0)
    assert math.isclose(result["slippage_usd"], 0.0)
    assert math.isclose(result["on_chain_fees_usd"], 1.5)
    assert math.isclose(result["net_profit_usd"], -1.5)
    assert math.isclose(result["net_margin_pct"], 0.0)
