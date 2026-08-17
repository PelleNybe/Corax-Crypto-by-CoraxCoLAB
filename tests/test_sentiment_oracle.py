import pytest
from unittest.mock import AsyncMock, patch
from intelligence.sentiment_oracle import SentimentOracle


@pytest.mark.asyncio
async def test_sentiment_oracle_analysis():
    oracle = SentimentOracle()
    score = await oracle._analyze_sentiment(
        "BTC sees massive surge and rally ahead of new adoption!"
    )
    assert score > 0.0

    score_bear = await oracle._analyze_sentiment(
        "Market crash expected, huge dump and hack reported."
    )
    assert score_bear < 0.0


@pytest.mark.asyncio
async def test_sentiment_oracle_emits_signal():
    oracle = SentimentOracle(assets=["BTC"])

    mock_news = [
        {"title": "BTC surge!", "body": "Huge bull rally", "source": "NewsA"},
        {"title": "Nothing happens", "body": "Boring day", "source": "NewsB"},
    ]

    # Mock network call
    oracle._fetch_news = AsyncMock(return_value=mock_news)

    emitted = []

    def callback(signal):
        emitted.append(signal)

    oracle.register_callback(callback)

    # Monkeypatch sleep to exit loop
    async def mock_sleep(seconds):
        oracle.stop()

    with patch("asyncio.sleep", new=mock_sleep):
        await oracle.start()

    # Should only emit for the first article due to high positive sentiment matching BTC
    assert len(emitted) == 1
    assert emitted[0].asset == "BTC"
    assert emitted[0].sentiment_score > 0.3
    assert emitted[0].source == "NewsA"
