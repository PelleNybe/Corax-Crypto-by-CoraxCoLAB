import asyncio
from typing import Callable, Coroutine, Any, Dict
from loguru import logger


class RedisEventBus:
    """
    Distributed Event Bus using Redis pub/sub (Mocked via asyncio queues for self-contained runtime here,
    but designed to be easily swapped with aioredis).
    Allows decoupled microservices (DataNode, StrategyNode, ExecutionNode).
    """

    def __init__(self):
        # In a real implementation this would use aioredis.from_url()
        self.channels: Dict[str, list[Callable[[str], Coroutine[Any, Any, Any]]]] = {}
        self.queues: Dict[str, asyncio.Queue] = {}

    async def publish(self, channel: str, message: dict):
        if channel not in self.queues:
            self.queues[channel] = asyncio.Queue()
        await self.queues[channel].put(message)
        logger.debug(
            f"[EventBus] Published to {channel}: {message.get('type', 'data')}"
        )

    async def subscribe(
        self, channel: str, callback: Callable[[dict], Coroutine[Any, Any, Any]]
    ):
        if channel not in self.channels:
            self.channels[channel] = []
            if channel not in getattr(self, "_active_listeners", {}):
                if not hasattr(self, "_active_listeners"):
                    self._active_listeners = {}
                self._active_listeners[channel] = asyncio.create_task(
                    self._listen(channel)
                )
        self.channels[channel].append(callback)
        logger.info(f"[EventBus] Subscribed to {channel}")

    async def _listen(self, channel: str):
        if channel not in self.queues:
            self.queues[channel] = asyncio.Queue()

        while True:
            message = await self.queues[channel].get()
            callbacks = self.channels.get(channel, [])

            # Execute all callbacks concurrently
            if callbacks:
                tasks = [cb(message) for cb in callbacks]
                await asyncio.gather(*tasks, return_exceptions=True)


event_bus = RedisEventBus()
