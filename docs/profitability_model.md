# Profitability Model & Cost Calculus

Corax Crypto requires real-world profitability analysis before executing high-frequency arbitrage logic across integrated CEX endpoints (Binance, Bybit, OKX, Bitget) and on-chain bridges (Circle CCTP / Arc). The `execution/profit_calculator.py` module handles these calculations dynamically to ensure trades are only executed when net-positive margins are guaranteed.

## Architecture & Integration

The calculator is embedded natively within the `ArbitrageEngine` (`_analyze_spread` method). Rather than firing executions merely on gross spread thresholds, the system dynamically prices execution friction in real time.

It is specifically designed around the zero-copy, multi-threaded **Polars** engine to allow vectorised profitability scanning over massive Parquet historical data structures via the `get_net_margin_expr()` class method.

---

## Cost Variables Breakdown

### 1. Centralized Exchange (CEX) Trading Fees
Fees represent a fixed, volume-based penalty subtracted from gross margins.

- We apply a conservative standard Tier-0 **Taker Fee** model across all platforms as arbitrage inherently utilizes taker liquidity.
- **Binance / Bybit / Bitget:** 0.1% (10 bps) Taker.
- **OKX:** 0.1% (10 bps) Taker.

*Formula: `Taker Fee = Trade Size (USD) * (Buy Exchange Fee % + Sell Exchange Fee %)`*

### 2. Slippage Estimations & Penalty Buffer
We assess slippage penalties structurally rather than stochastically, based directly on L2 top-of-book depth.

- **Base Slippage:** A fixed 1 bps (0.0001) penalty is applied across all operations to account for network latency between the WebSockets ingestion and execution endpoint.
- **Top-of-Book Penalty:** If the attempted trade size (base currency) exceeds the available depth at the best Bid or Ask, a severe **0.5%** penalty rate is applied proportionally to the overflow size.

*Formula: `Slippage (USD) = (Overflow Base Amount * Order Price * 0.005) + (Total Base Amount * Order Price * 0.0001)`*

### 3. On-Chain Settlement Costs
Because Corax relies on on-chain liquidity routing and Circle CCTP for inter-exchange capital balancing, a fixed USD gas/bridge buffer is applied.

- **Standard On-Chain Deduction:** $1.50 flat per operation cycle.

---

## The Execution Threshold

The Arbitrage Engine implements the calculations and strictly enforces the `min_net_margin_pct` threshold. Currently set to **0.05%**, an execution signal will only be passed to the Order Manager if the equation yields:

`Net Profit (USD) = Gross Profit (USD) - CEX Fees (USD) - Slippage (USD) - On-Chain Fees (USD)`

Where:
`Net Margin (%) = (Net Profit / Trade Size) * 100 > 0.05%`

---

## Polars-Native Vectorised Performance

To meet the high-speed requirements of the HFT Darwin Engine, `ProfitCalculator.get_net_margin_expr()` exposes a Polars Expression (`pl.Expr`). This allows the system to calculate net margin across entire orderbook dataframes simultaneously without ever loading the data into Python memory objects (bypassing the GIL).

```python
# Example Polars implementation
df = df.with_columns(
    net_margin=ProfitCalculator.get_net_margin_expr(
        ask_col="best_ask",
        bid_col="best_bid",
        exchange_buy="binance",
        exchange_sell="okx"
    )
)
```
