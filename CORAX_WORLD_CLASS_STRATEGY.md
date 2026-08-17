# Corax Crypto: Systematic Implementation Strategy for World-Class Parity

This document outlines the comprehensive, production-ready strategy to systematically implement the 8 critical architectural epics required to elevate Corax Crypto to a world-class institutional and top-tier retail platform.

**Core Directives for Implementation:**
*   **Zero Mockups:** All code must be 100% fully functional and interact with live APIs or valid testnets.
*   **Asynchronous First:** All I/O, network requests, and inter-process communication must utilize non-blocking `asyncio`.
*   **Polars Native:** All data manipulation must avoid Python-level iteration in favor of vectorized Polars `LazyFrame`/`DataFrame` operations.
*   **Fail-Fast Security:** Missing secrets or configurations must crash the system at boot, not at runtime.

---

## Phase 1: Institutional Execution & Order Management (Epics 1 & 2)
**Objective:** Replace instantaneous monolithic orders with advanced algorithmic slicing (TWAP/VWAP/Iceberg) and implement Trailing Take Profit (TTP) for Smart Trades.

### 1. Advanced Execution Algorithms
*   **Architecture:** Create a new module `core.execution.algo_router`.
*   **Implementation:**
    *   **TWAP/VWAP:** Define `BaseExecutionAlgo(ABC)`. Implement `TWAPManager` that takes a total order size, a time window (e.g., 60 mins), and slices it into N chunks. It uses `asyncio.sleep` (non-blocking) between slices.
    *   **Iceberg:** Implement `IcebergManager` that submits a limit order for a fraction (e.g., 10%) of the total size. Subscribe to WebSocket order updates (`ccxt.pro.watch_orders`); upon receiving a `closed`/`filled` status, immediately fire the next chunk.
*   **Files Modified:** `core/execution/order_manager.py`, `schemas/orders.py` (add `ExecutionType` enum).
*   **Production Readiness:** Ensure partial fill handling. If a chunk fails, the router must pause, recalculate remaining volume, and retry or abort based on the `RiskManager` circuit breaker.

### 2. Smart Trades & Trailing Take Profit (TTP)
*   **Architecture:** Extend `core.execution.risk_manager.RiskManager`.
*   **Implementation:**
    *   Add `activation_price` and `trailing_deviation` to `Position` schema in `schemas/orders.py`.
    *   In the async `RiskManager.monitor_positions()` loop, track peak price *only after* the position PnL exceeds the `activation_price` (e.g., +10%).
    *   If current price drops below `peak_price * (1 - trailing_deviation)`, trigger an immediate market sell.
*   **Data Flow:** Utilizes the exact, non-contaminated `get_summary()` price from `core.state.GlobalState`.

---

## Phase 2: Market Expansion & Scalability (Epics 3, 4 & 5)
**Objective:** Support derivatives, Grid trading, and multi-account routing.

### 3. Futures, Perpetuals, and Margin Support
*   **Architecture:** Dynamic market type configuration.
*   **Implementation:**
    *   Update `core.config.Settings` to accept `MARKET_TYPE` (spot, future, swap).
    *   In `core.execution.exchange_manager`, when initializing `ccxt.pro`, set `options={'defaultType': settings.MARKET_TYPE}`.
    *   **Derivatives Logic:** Update order placement parameters to include `reduceOnly` for closing positions, and implement a `set_leverage(symbol, leverage)` API call upon engine boot.
    *   **Risk:** Update `RiskManager` to track `liquidationPrice` (parsed from exchange WebSockets) and force-close before exchange liquidation.

### 4. Grid Trading Architecture
*   **Architecture:** Build `core.strategies.grid_manager`.
*   **Implementation:**
    *   Define `GridState` schema (list of paired limit buy/sell levels).
    *   Use CCXT's `create_orders` (bulk order API) if supported, else `asyncio.gather()` for parallel placement of the initial grid.
    *   Listen to `watch_orders`. When a Buy limit is filled, instantly dispatch the corresponding Sell limit above it, and vice versa.
*   **Production Readiness:** Must handle network disconnects by querying `fetch_open_orders` upon reconnection and reconciling the local `GridState` with the exchange.

### 5. Multi-Account API Routing
*   **Architecture:** Refactor single-account logic into an `AccountManager`.
*   **Implementation:**
    *   Instead of a single CCXT instance, instantiate a dictionary mapping `account_id` -> `ccxt.pro.<exchange>()`.
    *   When the Engine generates a trade signal, `OrderManager` iterates over the `AccountManager`.
    *   It queries `fetch_balance` for each account, sizes the order proportionately (e.g., 5% of available USDT), and executes concurrently using `await asyncio.gather(*[ccxt_instance.create_order(...)])`.

---

## Phase 3: Enterprise Infrastructure & Security (Epic 6)
**Objective:** Decouple the monolith and secure secrets dynamically.

### 6. Distributed Microservices & Vault Security
*   **Architecture:** Message Broker (Redis/ZeroMQ) and dynamic secret fetching.
*   **Implementation:**
    *   **Event Bus:** Introduce `aioredis` (Redis pub/sub) or `aiozmq`. Break the monolith into 3 services:
        1.  `corax_data_node`: Connects to CCXT WebSockets, normalizes ticks, and publishes to Redis `topic:market_data`.
        2.  `corax_strategy_node`: Subscribes to `market_data`, runs Polars calculations/AI inference, publishes `topic:signals`.
        3.  `corax_execution_node`: Subscribes to `signals`, checks Risk, and executes on CCXT.
    *   **Security:** Integrate `hvac` (HashiCorp Vault Python client). At boot, the node authenticates using an AppRole/Token, requests the CCXT API keys, and stores them *only* in volatile memory. `.env` files will only hold the Vault Token.
*   **Production Readiness:** Implement heartbeat monitoring and automatic failover if the data node goes down.

---

## Phase 4: Institutional Testing & Alternative Data (Epics 7 & 8)
**Objective:** Flawless simulation and bleeding-edge data ingestion.

### 7. Tick-Level Event-Driven Backtesting
*   **Architecture:** Build `core.backtester.event_engine`.
*   **Implementation:**
    *   Unlike the vectorized Polars backtester, this requires iterating through high-resolution Parquet tick data.
    *   **To maintain speed:** Load the Parquet file into memory as an Arrow Table. Use a numba-jitted loop or highly optimized Python generator to yield ticks.
    *   Maintain a `SimulatedOrderBook` that tracks L2 depth. Limit orders must calculate Queue Position and only fill when historical volume traded at that price exceeds the queue size.
    *   Inject artificial latency (+50ms) to simulate real-world conditions.

### 8. Alternative Data (Mempool/NLP) & Visual Strategy Builder
*   **Architecture:** `Web3Bridge` expansion and UI WebSocket streaming.
*   **Implementation (Alt Data):**
    *   **Mempool:** Connect `AsyncWeb3` to an alchemy/infura WSS endpoint. Subscribe to `newPendingTransactions`. Decode hex payloads to identify large DEX swaps before they are mined.
    *   **NLP:** Connect to Telegram API (`Telethon`). Stream messages into a local optimized LLM/FinBERT model (run via `asyncio.to_thread` to prevent blocking) to yield sentiment scores [-1 to 1] into the `GlobalState`.
*   **Implementation (UI Builder):**
    *   Integrate `LiteGraph.js` into the `ui/` frontend.
    *   Users build a graph. The UI sends a JSON payload to the FastAPI backend.
    *   Backend implements a `StrategyCompiler` that parses the JSON into dynamic Polars `.with_columns()` chaining, converting a visual graph into a compiled `LazyFrame` execution plan.

---

## Execution Pipeline & Rollout
1.  **Foundation:** Implement Phase 3 (Vault + Redis) first to ensure scalable architecture.
2.  **Core Trading:** Implement Phase 2 (Derivatives + Multi-Account) as it directly impacts profitability and scale.
3.  **Algorithmic Edge:** Implement Phase 1 (TWAP/VWAP/Grid) utilizing the new distributed architecture.
4.  **Advanced Research:** Implement Phase 4 (Tick Backtesting + Alt Data + UI) to provide quantitative analysts the tools to refine strategies.

*Note: All implementations must include strict `pytest-asyncio` coverage and utilize `loguru` for extensive telemetry.*
