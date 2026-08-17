import time
from unittest.mock import patch, MagicMock

# mock environment so we can import Settings
with patch.dict(
    "os.environ",
    {
        "EXCHANGE_API_KEY": "mock",
        "EXCHANGE_API_SECRET": "mock",
        "LLM_API_KEY": "mock",
        "CIRCLE_API_KEY": "mock",
        "CIRCLE_WALLET_ID": "mock",
        "CIRCLE_ENTITY_SECRET": "mock",
    },
):
    from core.arc_ledger import ArcLedger


def benchmark_sync():
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "tokenBalances": [{"token": {"symbol": "USDC"}, "amount": "100.0"}]
            }
        }
        mock_get.return_value = mock_resp

        # mock sleep inside requests to simulate I/O
        def mock_get_side_effect(*args, **kwargs):
            time.sleep(0.05)
            return mock_resp

        mock_get.side_effect = mock_get_side_effect

        ledger = ArcLedger(initial_capital=100.0)
        start = time.time()
        for _ in range(50):
            ledger._last_sync_time = 0
            ledger._sync_balance_sync(force=True)
        print("sync time requests:", time.time() - start)


benchmark_sync()
