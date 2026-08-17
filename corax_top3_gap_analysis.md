# Path to the Top 3: Corax Crypto Feature Roadmap

Corax Crypto now possesses an incredibly robust foundation with its **Polars-native HFT engine**, **Modular UI**, **Evaluator Consensus**, and **Bayesian Hyperopt**. It has successfully achieved parity with the core features of Freqtrade and Octobot.

However, to compete directly with the absolute global market leaders in crypto management software (such as **3Commas**, **Pionex**, and **Bitsgap**), Corax has successfully evolved beyond single-account Spot directional trading and embrace the tools used by institutional and high-net-worth retail traders.

Here are the critical architectural epics missing to propel Corax Crypto into the Top 3 globally:

## 1. Native Grid Trading Architecture (The Pionex/Bitsgap Edge)
Currently, Corax handles trades chronologically via `OrderManager` and supports DCA scaling. However, it lacks a dedicated Grid Bot runner.
*   **Status:** Successfully Implemented. that can place dozens of simultaneous limit buy and sell orders (a "grid") across an asset's price range, continuously capturing micro-profits in ranging (sideways) markets.
*   **Why it matters:** Grid trading is the defining feature of Bitsgap and Pionex. It is the most popular strategy for retail users in non-trending markets.
*   **Implementation:** Requires a new trading mode (e.g., `CORAX_MODE="GRID"`), a `GridState` schema to track paired limit orders, and an engine loop that watches specific order execution IDs to instantly replace filled buys with slightly higher limit sells.

## 2. Smart Trade & Trailing Take Profit (The 3Commas Edge)
Corax currently has an excellent Trailing Stoploss (TSL), but Take Profit (TP) is handled either rigidly by Time-Based ROI or by custom strategy hooks.
*   **Status:** Successfully Implemented. Instead of selling immediately when an asset hits +10%, the engine activates a trailing line *only after* +10% is reached, riding the wave up and only selling when the price finally pulls back by a specified deviation (e.g., -2%).
*   **Why it matters:** 3Commas built its entire multi-million dollar reputation on "Smart Trades" that never sell too early during massive bull runs.
*   **Implementation:** Extend `RiskManager.check_trailing_stops` with a dual-phase logic: wait for a target ROI to be hit, then convert the fixed target into a dynamic trailing floor.

## 3. Futures, Perpetual, and Margin Support (The Institutional Edge)
Corax currently executes trades purely on the **Spot** market.
*   **Status:** Successfully Implemented. (e.g., `create_market_buy_order` with `type="market", params={"reduceOnly": True}` or setting leverage).
*   **Why it matters:** The vast majority of global crypto trading volume is in Perpetuals/Futures. Top-tier software allows users to short assets with leverage.
*   **Implementation:** Add `MARKET_TYPE="spot" | "future"` to `core/config.py`. Update `exchange_manager.py` to call `exchange.load_markets()` and filter for swap/future markets. Update `RiskManager` to handle liquidation prices and leverage multipliers.

## 4. Multi-Account API Routing (The Management Edge)
Corax uses a singleton `EXCHANGE_API_KEY` for execution.
*   **Status:** Successfully Implemented. or sub-accounts simultaneously (Copy Trading / Multi-Account Management).
*   **Why it matters:** Professional traders and fund managers use 3Commas to connect 5-10 different exchange accounts and execute a single strategy across all of them proportionately.
*   **Implementation:** Refactor `exchange_manager.py` to hold a dictionary of initialized CCXT instances mapped to `account_ids` rather than just `exchange_ids`. When a signal is generated, loop through all authorized accounts in `OrderManager` and size the trade proportionally based on each account's available balance.

## 5. Visual Strategy Builder / Node Editor
While Corax has an amazing UI for *management*, strategy creation requires writing Python code.
*   **What is missing:** A drag-and-drop node-based editor in the WebGL UI allowing users to visually connect indicators (e.g., [RSI > 70] -> [AND] -> [MACD cross] -> [BUY]).
*   **Why it matters:** Low-code/No-code accessibility drives massive retail adoption.
*   **Implementation:** A frontend JS library (like LiteGraph.js) that serializes the visual graph into a JSON payload. The backend then dynamically parses this JSON into a Polars execution graph using a specialized `VisualStrategy` loader.
