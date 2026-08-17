import asyncio
from typing import Dict, Any, Callable
import aiohttp
import time
from loguru import logger
from web3 import AsyncWeb3
from web3.providers.rpc import AsyncHTTPProvider


class WhaleTracker:
    """
    Monitors EVM chains for large movements (Whales) via Async RPC.
    Feeds 'Whale Action' signals to the core engine.
    """

    def __init__(self, rpc_url: str, min_transfer_usd: float = 1_000_000):
        self.rpc_url = rpc_url
        self.min_transfer_usd = min_transfer_usd
        self.w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))
        self.callbacks = []
        self.is_running = False
        self._eth_price = 3000.0
        self._last_price_fetch = 0

        # We only really care about stablecoins for generic whale tracking
        self.token_addresses = {
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eb48",
        }

        # Minimal ERC20 ABI for Transfer event
        self.erc20_abi = [
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "name": "from", "type": "address"},
                    {"indexed": True, "name": "to", "type": "address"},
                    {"indexed": False, "name": "value", "type": "uint256"},
                ],
                "name": "Transfer",
                "type": "event",
            }
        ]

    def register_callback(self, cb: Callable[[Dict[str, Any]], None]):
        self.callbacks.append(cb)

    async def _emit(self, data: Dict[str, Any]):
        tasks = []
        for cb in self.callbacks:
            if asyncio.iscoroutinefunction(cb):
                tasks.append(cb(data))
            else:
                cb(data)
        if tasks:
            await asyncio.gather(*tasks)

    async def start(self):
        """Starts the infinite monitoring loop."""
        if not await self.w3.is_connected():
            logger.error("🐋 WhaleTracker: Could not connect to RPC")
            return

        logger.info(
            f"🐋 WhaleTracker started. Monitoring > ${self.min_transfer_usd:,.0f} transfers"
        )
        self.is_running = True

        # We'll poll the latest block
        latest_block = await self.w3.eth.block_number

        try:
            while self.is_running:
                await self._update_eth_price()
                current_block = await self.w3.eth.block_number
                if current_block > latest_block:
                    for i in range(latest_block + 1, current_block + 1):
                        await self._process_block(i)
                    latest_block = current_block
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("🐋 WhaleTracker task cancelled.")

    def stop(self):
        self.is_running = False
        self._eth_price = 3000.0
        self._last_price_fetch = 0

    async def _update_eth_price(self):
        # Fetch real ETH price every 60 seconds
        now = time.time()
        if now - self._last_price_fetch > 60:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT",
                        timeout=5,
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            self._eth_price = float(data.get("price", self._eth_price))
                            self._last_price_fetch = now
            except Exception as e:
                logger.warning(f"Failed to fetch real-time ETH price: {e}")

    async def _process_block(self, block_number: int):
        try:
            block = await self.w3.eth.get_block(block_number, full_transactions=True)
            for tx in block.transactions:
                # Check native ETH transfer
                eth_value = self.w3.from_wei(tx.value, "ether")
                usd_value = float(eth_value) * self._eth_price

                if usd_value >= self.min_transfer_usd:
                    logger.warning(
                        f"🚨 WHALE DETECTED: {eth_value:.2f} ETH (${usd_value:,.2f}) moved in tx {tx.hash.hex()}"
                    )
                    await self._emit(
                        {
                            "type": "whale_movement",
                            "asset": "ETH",
                            "usd_value": usd_value,
                            "tx_hash": tx.hash.hex(),
                        }
                    )

                # Optional: Handle ERC20 Tokens
                if tx.to in self.token_addresses.values():
                    input_data = getattr(tx, "input", b"")
                    if isinstance(input_data, bytes):
                        hex_input = input_data.hex()
                    else:
                        hex_input = input_data

                    # Strip 0x if present
                    if hex_input.startswith("0x"):
                        hex_input = hex_input[2:]

                    # Parse standard ERC20 transfer `0xa9059cbb`
                    if hex_input.startswith("a9059cbb"):
                        # Extract the amount from the data payload (last 32 bytes/64 hex chars)
                        try:
                            hex_amount = hex_input[-64:]
                            token_amount = int(hex_amount, 16)
                            # Assuming 6 decimals for USDC/USDT
                            token_usd = token_amount / 1_000_000

                            if token_usd >= self.min_transfer_usd:
                                logger.warning(
                                    f"🚨 STABLECOIN WHALE: ${token_usd:,.2f} moved in tx {tx.hash.hex()}"
                                )
                                await self._emit(
                                    {
                                        "type": "whale_movement",
                                        "asset": "USDC/USDT",
                                        "usd_value": token_usd,
                                        "tx_hash": tx.hash.hex(),
                                    }
                                )
                        except Exception as e:
                            logger.error(f"Failed to parse ERC20 transfer payload: {e}")

        except Exception as e:
            logger.error(f"WhaleTracker error parsing block {block_number}: {e}")
