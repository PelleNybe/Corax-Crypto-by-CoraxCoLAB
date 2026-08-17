import time
import asyncio
from unittest.mock import patch, AsyncMock

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
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json.return_value = {
            "data": {
                "tokenBalances": [{"token": {"symbol": "USDC"}, "amount": "100.0"}]
            }
        }
        mock_resp.__aenter__.return_value = mock_resp
        mock_get.return_value = mock_resp

        # mock sleep inside requests to simulate I/O
        def mock_get_side_effect(*args, **kwargs):
            mock_ctx = AsyncMock()

            async def enter(*a, **kw):
                await asyncio.sleep(0)
                return mock_resp

            mock_ctx.__aenter__ = enter
            return mock_ctx

        mock_get.side_effect = mock_get_side_effect

        ledger = ArcLedger(initial_capital=100.0)

        # Test in a synchronous environment (should create an event loop)
        start = time.time()
        for _ in range(50):
            ledger._last_sync_time = 0
            ledger._sync_balance_sync(force=True)
        print("sync time asyncio.run:", time.time() - start)

        # Test in an asyncio environment
        async def run_in_loop():
            start2 = time.time()
            for _ in range(50):
                ledger._last_sync_time = 0
                ledger._sync_balance_sync(force=True)
            print("sync time create_task:", time.time() - start2)

        asyncio.run(run_in_loop())


benchmark_sync()
