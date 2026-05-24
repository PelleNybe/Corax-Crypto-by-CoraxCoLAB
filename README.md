<div align="center">
  <img src="assets/coraxcryptologo.png" alt="Corax Crypto Logo" width="400" />

  <h1 style="color: #00ffcc; text-transform: uppercase; letter-spacing: 2px;">Corax Crypto: Autonomous HFT Agent</h1>
  <p style="font-size: 1.2rem; color: #a0aec0; margin-bottom: 20px;">
    <i>Quantum Spatial Interface • 100% Polars-Native Execution • Web3 Cross-Chain Bridging</i>
  </p>

  <!-- Badges -->
  <p>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" /></a>
    <a href="https://pola.rs/"><img src="https://img.shields.io/badge/Polars-Blazing_Fast-cd792c?style=for-the-badge&logo=polars&logoColor=white" alt="Polars" /></a>
    <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-Async_Core-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" /></a>
    <a href="https://docs.docker.com/"><img src="https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" /></a>
    <a href="https://www.circle.com/"><img src="https://img.shields.io/badge/Circle-W3S_Integration-8A2BE2?style=for-the-badge&logo=circle&logoColor=white" alt="Circle" /></a>
    <a href="https://threejs.org/"><img src="https://img.shields.io/badge/WebGL-Three.js-black?style=for-the-badge&logo=three.js&logoColor=white" alt="WebGL" /></a>
  </p>
</div>

<hr style="border: 1px solid #00ffcc; opacity: 0.3;" />

## ⚡ System Overview

**Corax Crypto** is a next-generation, asynchronous High-Frequency Trading (HFT) platform and Autonomous Economic Actor (AEA). Designed specifically for the **Agora Agents Hackathon (Pod 4)**, it bridges the gap between raw quantitative execution, decentralized on-chain settlement, and high-level macro intelligence.

Corax Crypto pioneers a new standard using a 100% **Polars-native** data pipeline, an asynchronous `ccxt.pro` execution loop, and a stunning Cyberpunk-themed 3D WebGL Command Center.

<hr style="border: 1px dashed #333;" />

## 🏆 Hackathon RFB Achievements

We have pushed the boundaries of what an automated trading agent can do. Here are our core implementations for the hackathon:

<details>
<summary><b>🔥 1. High-Frequency Data Pipelines (Polars Native)</b></summary>
<br>

Legacy systems choke on Pandas objects. Corax Crypto utilizes a **zero-copy, multi-threaded Polars backend**.
* **Streaming Execution:** Utilizes Polars `LazyFrames` to seamlessly process massive historical Parquet datasets from NVMe drives without loading unoptimized objects into RAM.
* **Columnar Ingestion:** WebSocket ticks are converted directly to columnar formats before dataframe creation, yielding massive ingestion performance boosts suitable for millisecond-level arbitrage.
* **Strictly No Pandas:** A complete rewrite of the data engine ensures deterministic, high-speed evaluations using true vectorized Polars evaluations.
</details>

<details>
<summary><b>🧠 2. Social Ensemble AI & Portfolio Manager</b></summary>
<br>

Trading is no longer just quantitative; it's narrative-driven.
* **Regime-Switching Architecture:** The engine continuously analyzes market micro-structure to classify environments (volatile, ranging, trending) and adapt parameters.
* **LLM Copilot Synthesis:** Integrates async LLMs (OpenAI/Gemini) to parse social sentiment, synthesize macro-economic state summaries, and provide human operators with actionable insights.
* **NLP Command Center:** Operators interact with the engine via Telegram using natural language (e.g., *"Hit the kill switch"*, *"What is the current status?"*).
</details>

<details>
<summary><b>⛓️ 3. Web3 Bridge & Circle CCTP Settlement</b></summary>
<br>

Bridging CeFi arbitrage with DeFi settlement.
* **Circle Web3 Services (W3S):** Fully integrated on-chain settlement using the Circle developer stack (`/w3s` API endpoints).
* **Cross-Chain Capital Routing:** Automates the movement of USDC profits via Circle's Cross-Chain Transfer Protocol (CCTP), enabling true autonomous economic agency across supported EVM chains.
* **AsyncWeb3 Telemetry:** Polls on-chain Ethereum RPCs to track predictive whale transactions and front-run liquidity shifts.
</details>

<hr style="border: 1px dashed #333;" />

## 📸 Media Showcase: The Quantum Command Center

Experience the market through our fully immersive 3D WebGL interface.

### 🌐 Corax Telemetry HUD
<div align="center">
  <img src="./docs/ui_screenshot.png" alt="CORAX TELEMETRY UI" width="90%" style="border: 1px solid #00ffcc; border-radius: 5px; box-shadow: 0 0 15px rgba(0, 255, 204, 0.2);" onerror="this.src='https://via.placeholder.com/800x450/0b0f19/00ffcc?text=CORAX+TELEMETRY+UI+[docs/ui_screenshot.png]';"/>
  <p><i>Live L2 Order Book visualization, reactive particle systems, and real-time LLM synthesis overlay.</i></p>
</div>

### 💬 NLP Telegram Command Center
<div align="center">
  <img src="./docs/telegram_bot.png" alt="Telegram Bot Interface" width="60%" style="border: 1px solid #a0aec0; border-radius: 5px;" onerror="this.src='https://via.placeholder.com/400x500/1e293b/a0aec0?text=TELEGRAM+COMMAND+CENTER+[docs/telegram_bot.png]';"/>
  <p><i>Natural language execution and emergency Risk Manager Kill Switch via aiogram.</i></p>
</div>

### 💻 Async Terminal Logs
<div align="center">
  <img src="./docs/terminal_logs.png" alt="Terminal Logs" width="90%" style="border: 1px solid #333; border-radius: 5px;" onerror="this.src='https://via.placeholder.com/800x300/000000/00ffcc?text=ASYNC+HFT+LOGS+[docs/terminal_logs.png]';"/>
  <p><i>Non-blocking asyncio loop handling simultaneous multiplexing across Binance, Bybit, and OKX.</i></p>
</div>

<hr style="border: 1px solid #00ffcc; opacity: 0.3;" />

## 🛠️ Architecture Deep-Dive

<details>
<summary><b>Click to explore the technical stack</b></summary>
<br>

*   **Core Engine:** Python 3.11+, fully non-blocking `asyncio` loop. `pydantic-settings` enforces a 'Fail-Fast' environment validation upon boot.
*   **Data Layer:** `Polars` for dataframes, `PyArrow` for Parquet data persistence. Millisecond-level HFT execution loop.
*   **API & Comms:** decoupled `FastAPI` + `Uvicorn` layer serving real-time WebSockets to the frontend.
*   **Trading:** `ccxt.pro` for async Level 2 depth streaming. Dynamic Profitability Calculator accounts for CEX fees, slippage, and on-chain bridge fees.
*   **UI/Visualization:** Vanilla JS, `Three.js` (WebGL) for the 3D Quantum Market Dashboard, `Lightweight Charts` for candlestick rendering.
*   **Risk Management:** Strict enforcement of max risk percentage, daily drawdown limits (Kill Switch), and dynamic ATR Trailing Stops.
</details>

<details>
<summary><b>🚀 Setup & Deployment Instructions</b></summary>
<br>

Corax Crypto uses a 'Fail-Fast' design. It will crash immediately at startup if required `.env` secrets are missing.

### Option A: Docker (Recommended)
```bash
git clone https://github.com/PelleNybe/corax-crypto.git
cd corax-crypto
cp .env.example .env
# Edit .env with your Circle W3S API keys and Exchange credentials
docker compose up -d --build
```

### Option B: Local Environment (Poetry)
*Requires `package-mode = false` in `pyproject.toml`.*
```bash
curl -sSL https://install.python-poetry.org | python3 -
poetry install
cp .env.example .env
poetry run python main.py
```
</details>

<hr style="border: 1px solid #00ffcc; opacity: 0.3;" />

## 👨‍💻 Visionaries Behind the Code

<div align="center" style="background: rgba(11, 15, 25, 0.8); padding: 30px; border-radius: 15px; border: 1px solid #00ffcc; box-shadow: 0 0 20px rgba(0, 255, 204, 0.1);">

  <img src="https://avatars.githubusercontent.com/u/10492815?v=4" alt="Pelle Nyberg" width="120" style="border-radius: 50%; border: 2px solid #00ffcc; box-shadow: 0px 4px 12px rgba(0,255,204,0.3); margin-bottom: 15px;" />

  <h2 style="color: #ffffff; margin: 0;">Pelle Nyberg</h2>
  <p style="color: #00ffcc; font-size: 1.1em; margin-top: 5px;"><em>CEO, Deep Tech Developer, AI & Robotics Innovator</em></p>

  <p style="color: #a0aec0; max-width: 600px; margin: 15px auto;">
    Pelle specializes in pushing the boundaries of autonomous systems, quantitative finance, and spatial computing.
  </p>

  <p>
    <a href="https://github.com/PelleNybe"><img src="https://img.shields.io/badge/GitHub-PelleNybe-181717?style=for-the-badge&logo=github" alt="GitHub" /></a>
    <a href="https://www.linkedin.com/in/pellenyberg/"><img src="https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=for-the-badge&logo=linkedin" alt="LinkedIn" /></a>
    <a href="https://pellenybe.github.io"><img src="https://img.shields.io/badge/Portfolio-Explore-4CAF50?style=for-the-badge&logo=safari" alt="Portfolio" /></a>
  </p>

  <br />
  <hr style="border: 1px dashed #333; width: 50%;" />
  <br />

  <h2 style="color: #ffffff; margin: 0;">Corax CoLAB</h2>
  <p style="color: #a0aec0; font-size: 1.1em; margin-top: 5px;"><em>Mission: Intelligent Automation and Deep Tech.</em></p>

  <p>
    <a href="https://coraxcolab.com"><img src="https://img.shields.io/badge/Company-Corax_CoLAB-FF5722?style=for-the-badge&logo=google-cloud" alt="Corax CoLAB" /></a>
    <a href="https://cryptop.coraxcolab.com"><img src="https://img.shields.io/badge/Platform-CryptoP-00BCD4?style=for-the-badge&logo=vercel" alt="CryptoP" /></a>
  </p>

</div>

<br>

<div align="center">
  <p style="color: #a0aec0; font-size: 0.9em;">
    &copy; 2026 Corax CoLAB. Licensed under the <a href="LICENSE" style="color: #00ffcc;">GPLv3 License</a>.
  </p>
</div>
