import asyncio
from typing import Dict, Any, Callable, List
from loguru import logger
import aiohttp
import re
from pydantic import BaseModel


class SentimentSignal(BaseModel):
    asset: str
    sentiment_score: float  # -1.0 to 1.0
    confidence: float
    source: str


class SentimentOracle:
    """
    Ingests macro news and social media feeds, passes them to an LLM Copilot for NLP
    sentiment scoring, and emits 'Sentiment Alpha' signals to the Engine.
    """

    def __init__(self, assets: List[str] = ["BTC", "ETH", "SOL"]):
        self.assets = assets
        self.callbacks = []
        self.is_running = False

        self.bullish_words = {"surge", "bull", "rally", "buy", "adoption", "up", "high"}
        self.bearish_words = {
            "crash",
            "bear",
            "dump",
            "sell",
            "ban",
            "down",
            "low",
            "hack",
        }

        # Using CryptoCompare News API as the data source
        self.feed_url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        self.word_pattern = re.compile(r"[a-z0-9]+")

    def register_callback(self, cb: Callable[[SentimentSignal], None]):
        self.callbacks.append(cb)

    async def _emit(self, signal: SentimentSignal):
        tasks = []
        for cb in self.callbacks:
            if asyncio.iscoroutinefunction(cb):
                tasks.append(cb(signal))
            else:
                cb(signal)
        if tasks:
            await asyncio.gather(*tasks)

    async def _fetch_news(self) -> List[Dict[str, Any]]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.feed_url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("Data", [])[:5]  # Top 5 latest news
        except Exception as e:
            logger.error(f"SentimentOracle fetch error: {e}")
        return []

    async def _analyze_sentiment(self, text: str) -> float:

        if not hasattr(self, "copilot"):
            from intelligence.copilot import CoraxCopilot

            self.copilot = CoraxCopilot()
        try:
            # Try to use the copilot but if it fails due to configuration, fallback to heuristics
            try:
                # Assuming Copilot has some form of call we can hijack. Let's just use generate_synthesis.
                # Actually we can just implement the heuristic fallback inside the exception block.
                response = await self.copilot.generate_synthesis(
                    {
                        "text_to_analyze": text,
                        "instruction": "Return ONLY a float between -1.0 and 1.0",
                    }
                )
                score = float(response.strip())
                return max(-1.0, min(1.0, score))
            except Exception as e:
                logger.warning(f"Sentiment Oracle LLM failure or parse error: {e}")

            # Heuristic fallback if LLM is unavailable (e.g. tests)
            text_lower = text.lower()

            words = set(self.word_pattern.findall(text_lower))
            score = (len(words & self.bullish_words) * 0.2) - (
                len(words & self.bearish_words) * 0.2
            )

            return max(-1.0, min(1.0, score))
        except Exception as e:
            logger.error(f"LLM Sentiment Oracle analysis failed: {e}")
            return 0.0

    async def start(self):
        """Starts the infinite monitoring loop."""
        logger.info(f"📰 SentimentOracle started. Monitoring news for {self.assets}")
        self.is_running = True

        import re

        # Pre-compute asset mapping and set for fast O(1) lookups
        asset_map = {asset.lower(): asset for asset in self.assets}
        asset_set = set(asset_map.keys())
        word_pattern = re.compile(r"[a-z0-9]+")

        try:
            while self.is_running:
                news_items = await self._fetch_news()
                for item in news_items:
                    body = item.get("body", "")
                    title = item.get("title", "")

                    # Only construct the combined string once
                    combined = f"{title} {body}"
                    combined_lower = combined.lower()

                    # See which assets are mentioned using fast set intersection
                    words = set(word_pattern.findall(combined_lower))
                    matched_assets = [asset_map[w] for w in (words & asset_set)]

                    if not matched_assets:
                        continue

                    # Analyze sentiment only once per news item, regardless of how many assets are mentioned
                    sentiment = await self._analyze_sentiment(combined)

                    if abs(sentiment) > 0.3:  # Only emit strong signals
                        for asset in matched_assets:
                            signal = SentimentSignal(
                                asset=asset,
                                sentiment_score=sentiment,
                                confidence=abs(sentiment),
                                source=item.get("source", "CryptoCompare"),
                            )
                            logger.info(
                                f"🧠 Sentiment Alpha [{asset}]: Score {sentiment:.2f} via '{title[:30]}...'"
                            )
                            await self._emit(signal)

                await asyncio.sleep(60 * 15)  # Fetch every 15 minutes
        except asyncio.CancelledError:
            logger.info("📰 SentimentOracle task cancelled.")

    def stop(self):
        self.is_running = False
