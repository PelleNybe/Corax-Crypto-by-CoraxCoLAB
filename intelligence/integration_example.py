# Example of how these intelligence modules plug into the Engine core
import asyncio
from intelligence.darwin_engine import DarwinEngine
from intelligence.whale_tracker import WhaleTracker
from intelligence.sentiment_oracle import SentimentOracle


class AdvancedIntelligenceManager:
    def __init__(self, engine):
        self.engine = engine
        self.darwin = DarwinEngine()
        self.whale = WhaleTracker("https://eth.llamarpc.com")
        self.sentiment = SentimentOracle()

    async def _handle_whale_signal(self, data):
        # Trigger an immediate volatility circuit breaker or adjustment
        if data["usd_value"] > 50_000_000:
            self.engine.risk_manager.adjust_volatility_multiplier(2.0)

    async def _handle_sentiment_signal(self, signal):
        # Add sentiment alpha to the global evaluator
        self.engine.evaluator.add_external_alpha(signal.asset, signal.sentiment_score)

    async def start_all(self):
        self.whale.register_callback(self._handle_whale_signal)
        self.sentiment.register_callback(self._handle_sentiment_signal)

        # In a real setup these would be background tasks on the main event loop
        asyncio.create_task(self.whale.start())
        asyncio.create_task(self.sentiment.start())

        # Start Darwin Engine optimization of the current strategy
        param_space = {"fast_len": (10, 20), "slow_len": (21, 50)}

        async def evaluate_strategy_fitness(params):
            return 1.0  # replace with actual backtest

        asyncio.create_task(
            self.darwin.start_evolution_loop(param_space, evaluate_strategy_fitness)
        )
