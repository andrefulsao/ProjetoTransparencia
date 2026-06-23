from __future__ import annotations

import asyncio
import time


class AsyncTokenBucket:
    """Simple async token bucket rate limiter measured in requests per minute."""

    def __init__(self, rate_per_minute: int) -> None:
        self.capacity = max(1, rate_per_minute)
        self.tokens = float(self.capacity)
        self.refill_rate = self.capacity / 60.0
        self.updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.updated_at
                self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
                self.updated_at = now

                if self.tokens >= 1:
                    self.tokens -= 1
                    return

                wait_seconds = (1 - self.tokens) / self.refill_rate
                await asyncio.sleep(wait_seconds)
