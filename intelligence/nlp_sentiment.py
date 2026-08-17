import asyncio
from loguru import logger


class FinBERTSentimentAnalyzer:
    """
    Alternative Data: NLP Sentiment Analysis.
    Loads a HuggingFace FinBERT model and processes raw text from X/Telegram.
    Runs inference in a background thread to prevent blocking the asyncio loop.
    """

    def __init__(self):
        logger.info("Initializing FinBERT NLP Sentiment Analyzer")
        self._model_loaded = False
        self.pipeline = None
        try:
            from transformers import pipeline

            # Using a fast, lightweight financial sentiment model
            self.pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
            self._model_loaded = True
            logger.success("FinBERT model loaded successfully.")
        except ImportError:
            logger.warning(
                "transformers library not installed. FinBERT sentiment will fallback to zero."
            )
        except Exception as e:
            logger.error(f"Failed to load FinBERT model: {e}")

    def _blocking_inference(self, text: str) -> float:
        """Runs actual ML inference."""
        if not self.pipeline:
            return 0.0

        try:
            # We take max 512 characters to prevent token limit errors
            results = self.pipeline(text[:512])
            result = results[0]
            label = result["label"]
            score = result["score"]

            # Map FinBERT labels (positive, negative, neutral) to [-1.0, 1.0]
            if label == "positive":
                return score
            elif label == "negative":
                return -score
            else:
                return 0.0

        except Exception as e:
            logger.error(f"FinBERT inference error: {e}")
            return 0.0

    async def analyze(self, text: str) -> float:
        """
        Asynchronously runs the sentiment inference.
        Returns a score between -1.0 (Extreme Bearish) and 1.0 (Extreme Bullish).
        """
        if not self._model_loaded:
            return 0.0

        # Strict Directive: Run CPU-bound ML tasks in thread pool
        score = await asyncio.to_thread(self._blocking_inference, text)
        logger.debug(f"NLP Sentiment Score for '{text[:20]}...': {score:.2f}")
        return score
