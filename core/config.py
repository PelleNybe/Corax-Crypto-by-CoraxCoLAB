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

    # Strategy
    ACTIVE_STRATEGY: str = Field(
        default="SmaCrossover",
        description="The name of the strategy class to load from the strategies/ directory",
    )

    # Exchange Credentials (Required)
    EXCHANGE_ID: str = Field(default="binance", description="Exchange to connect to")
    EXCHANGE_API_KEY: str = Field(..., description="Exchange API Key")
    EXCHANGE_API_SECRET: str = Field(..., description="Exchange API Secret")
    EXCHANGE_PASSPHRASE: str | None = Field(
        default=None, description="Exchange Passphrase (if required by exchange)"
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

    # LLM Copilot (Required)
    LLM_API_KEY: str = Field(
        ..., description="API Key for the LLM Copilot (e.g., OpenAI/Gemini)"
    )

    # Risk Parameters
    MAX_RISK_PER_TRADE_PCT: float = Field(
        default=0.01,
        description="Maximum risk allocation per trade (e.g., 0.01 for 1%)",
    )
    DAILY_DRAWDOWN_LIMIT_PCT: float = Field(
        default=0.05, description="Daily drawdown threshold to activate Kill Switch"
    )

    # Hardware Backend Configuration
    CORAX_HARDWARE_BACKEND: str = Field(
        default="CPU", description="Inference backend to load (CPU/EDGE_NPU)"
    )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


# Initialize settings singleton. This will immediately raise ValidationError if required fields are missing.
settings = Settings()
