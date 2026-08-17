import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from intelligence.whale_tracker import WhaleTracker


@pytest.fixture
def mock_w3():
    with patch("intelligence.whale_tracker.AsyncWeb3") as mock:
        mock_instance = mock.return_value
        # Use an AsyncMock for is_connected so await works
        mock_instance.is_connected = AsyncMock(return_value=True)
        # Setup mock eth property and its async methods
        mock_eth = MagicMock()
        mock_eth.block_number = 100
        mock_instance.eth = mock_eth

        # Setup block response
        mock_block = MagicMock()
        mock_tx1 = MagicMock()
        mock_tx1.value = 1000 * (10**18)  # 1000 ETH
        mock_tx1.hash.hex.return_value = "0x123"
        mock_tx1.to = "0xabc"

        mock_tx2 = MagicMock()
        mock_tx2.value = 1 * (10**18)  # 1 ETH
        mock_tx2.hash.hex.return_value = "0x456"
        mock_tx2.to = "0xdef"

        mock_block.transactions = [mock_tx1, mock_tx2]

        # We need get_block to return the block when awaited
        mock_eth.get_block = AsyncMock(return_value=mock_block)

        mock_instance.from_wei = lambda val, unit: val / (10**18)

        yield mock_instance


@pytest.mark.asyncio
async def test_whale_tracker_emits_signal(mock_w3):
    tracker = WhaleTracker("http://dummy", min_transfer_usd=1_000_000)
    # The fixture patched AsyncWeb3 class, but WhaleTracker instantiated it during import or creation.
    # Let's replace the w3 instance directly
    tracker.w3 = mock_w3

    # We need to monkeypatch the block loop logic slightly so it processes exactly 1 block and exits
    async def mock_sleep(seconds):
        tracker.stop()

    emitted = []

    def callback(data):
        emitted.append(data)

    tracker.register_callback(callback)

    with patch("asyncio.sleep", new=mock_sleep):
        # We need current_block > latest_block to trigger processing
        tracker.w3.eth.block_number = 101  # first call returns 101?
        # Actually it awaits it, but we can't easily make a property return different values when awaited unless it's a method
        # Let's just call _process_block directly
        await tracker._process_block(101)

    assert len(emitted) == 1
    assert emitted[0]["type"] == "whale_movement"
    assert emitted[0]["asset"] == "ETH"
    assert emitted[0]["usd_value"] == 1000 * 3000.0
