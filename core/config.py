from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """
    Core Configuration Manager using Pydantic.
    Enforces Fail-Fast design: if required env vars are missing, the app crashes immediately.
    """

    # Paper Trading / Dry Run Mode
    # Circle / Arc Ledger Configuration
    CIRCLE_API_KEY: str | None = Field(
        default=None, description="Circle Developer API Key"
    )
    CIRCLE_WALLET_ID: str | None = Field(default=None, description="Circle Wallet ID")
    CIRCLE_ENTITY_SECRET: str | None = Field(
        default=None, description="Circle Entity Secret"
    )
    USE_ARC_LEDGER: bool = Field(
        default=False, description="Use ArcLedger with real USDC instead of PaperLedger"
    )
    DRY_RUN_MODE: bool = Field(
        default=True,
        description="Enable Paper Trading (bypasses live exchange execution)",
    )
    PAPER_BALANCE_USDT: float = Field(
        default=10000.0, description="Initial balance for paper trading wallet"
    )

    # Environment
    CORAX_ENV: str = Field(
        default="development", description="Environment type (development/production)"
    )
    CORAX_MODE: str = Field(default="mainnet", description="Mode (mainnet/testnet)")

    # Visual Strategy Builder
    VISUAL_STRATEGY_PATH: str = Field(
        default="data/visual_strategy.json",
        description="Path to the JSON representation of the visual node strategy",
    )

    # Strategy
    ACTIVE_STRATEGY: str = Field(
        default="SmaCrossover",
        description="The name of the strategy class to load from the strategies/ directory",
    )

    # Market Configuration
    MARKET_TYPE: str = Field(
        default="spot", description="Market type to trade: 'spot', 'future', or 'swap'"
    )
    LEVERAGE: int = Field(
        default=1, description="Leverage multiplier for futures/margin trading"
    )

    # Exchange Credentials (Required)
    EXCHANGE_ID: str = Field(default="binance", description="Exchange to connect to")
    EXCHANGE_API_KEY: str = Field(..., description="Exchange API Key")
    EXCHANGE_API_SECRET: str = Field(..., description="Exchange API Secret")
    EXCHANGE_PASSPHRASE: str | None = Field(
        default=None, description="Exchange Passphrase (if required by exchange)"
    )

    # Multi-Account / Copy Trading
    MULTI_ACCOUNT_CONFIG: str = Field(
        default="{}",
        description='JSON string mapping account_id to credentials. e.g. {"sub1": {"exchange": "binance", "api_key": "x", "secret": "y"}}',
    )
    COPY_TRADE_ENABLED: bool = Field(
        default=False,
        description="Execute signals across all configured accounts proportionally",
    )
    # Arbitrage Exchanges
    ARBITRAGE_EXCHANGES: list[str] = Field(
        default=["binance", "kraken"],
        description="List of exchanges for arbitrage engine",
    )

    # Telegram Interface
    TELEGRAM_BOT_TOKEN: str | None = Field(
        default=None, description="Telegram Bot Token"
    )
    TELEGRAM_CHAT_ID: str | None = Field(
        default=None, description="Authorized Telegram Chat ID"
    )

    # LLM Copilot (Required)
    LLM_API_KEY: str = Field(
        ..., description="API Key for the LLM Copilot (e.g., OpenAI/Gemini)"
    )

    # Smart Trade / Trailing Take Profit
    TTP_ACTIVATION_PCT: float = Field(
        default=0.05,
        description="Profit percentage required to activate Trailing Take Profit",
    )
    TTP_TRAILING_PCT: float = Field(
        default=0.015, description="Trailing pullback percentage once TTP is activated"
    )

    # Grid Trading Parameters
    GRID_UPPER_PRICE: float = Field(
        default=70000.0, description="Upper bound for Grid Trading bot"
    )
    GRID_LOWER_PRICE: float = Field(
        default=50000.0, description="Lower bound for Grid Trading bot"
    )
    GRID_LEVELS: int = Field(default=20, description="Number of grid lines")
    # Risk Parameters
    MAX_RISK_PER_TRADE_PCT: float = Field(
        default=0.01,
        description="Maximum risk allocation per trade (e.g., 0.01 for 1%)",
    )
    DAILY_DRAWDOWN_LIMIT_PCT: float = Field(
        default=0.05, description="Daily drawdown threshold to activate Kill Switch"
    )

    # Hardware Backend Configuration
    DATA_PERSISTENCE_PATH: str = Field(default="./data", description="Data path")
    CORAX_HARDWARE_BACKEND: str = Field(
        default="CPU", description="Inference backend to load (CPU/EDGE_NPU)"
    )
    DATA_PERSISTENCE_PATH: str = Field(
        default="./data", description="Data persistence path"
    )

    # Data Persistence
    DATA_PERSISTENCE_PATH: str = Field(
        default="data/", description="Path for data persistence files"
    )

    # API Settings

    API_SECRET_KEY: str = Field(..., description="Secret key for API authentication")
    API_ALLOWED_ORIGINS: str = Field(
        default="http://localhost,http://localhost:8000,http://127.0.0.1:8000,http://127.0.0.1",
        description="Comma-separated list of allowed origins for CORS",
    )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


# Initialize settings singleton. This will immediately raise ValidationError if required fields are missing.
settings = Settings()
