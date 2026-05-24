import pytest
import os
from unittest.mock import AsyncMock, patch
from data_engine.downloader import HistoricalDataDownloader


@pytest.fixture
def mock_exchange():
    with patch("data_engine.downloader.ccxt.binance") as mock_binance:
        mock_instance = AsyncMock()
        # Mock fetch_ohlcv to return one chunk then empty
        mock_instance.fetch_ohlcv.side_effect = [
            [[1672531200000, 16000.0, 16100.0, 15900.0, 16050.0, 100.5]],
            [],
        ]
        mock_instance.close = AsyncMock()
        mock_binance.return_value = mock_instance
        yield mock_binance


@pytest.mark.asyncio
async def test_downloader_saves_parquet(mock_exchange):
    downloader = HistoricalDataDownloader("binance")

    await downloader.download_ohlcv("BTC/USDT", "1h", "2023-01-01T00:00:00Z", limit=1)

    file_path = "data/historical/BTC_USDT_1h.parquet"
    assert os.path.exists(file_path)

    # Cleanup
    if os.path.exists(file_path):
        os.remove(file_path)
