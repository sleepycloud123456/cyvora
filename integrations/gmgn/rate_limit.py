"""Client-side leaky bucket matching the documented GMGN plan weights."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from integrations.gmgn.constants import PLAN_BUCKETS
from integrations.gmgn.errors import GMGNError


class GMGNRateLimiter:
    """Wait until the local bucket can pay a route's weight.

    The default plan is free (5 tokens of capacity, refilled at 5 per second).
    A route whose weight is above the capacity can never succeed on that plan,
    which matches GMGN's ``PLAN_UPGRADE_REQUIRED`` behavior. CYVORA does not
    change the plan by itself.
    """

    def __init__(
        self,
        plan: str,
        *,
        clock: Callable[[], float],
        sleeper: Callable[[float], Awaitable[None]],
    ) -> None:
        if plan not in PLAN_BUCKETS:
            raise ValueError(f"Unknown GMGN plan {plan!r}.")
        rate, capacity = PLAN_BUCKETS[plan]
        self.plan = plan
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._updated = clock()
        self._clock = clock
        self._sleeper = sleeper
        self._lock: asyncio.Lock | None = None

    async def acquire(self, weight: int) -> None:
        if weight > self.capacity:
            raise GMGNError(
                f"Route weight {weight} exceeds the {self.plan} bucket capacity "
                f"{self.capacity:g}. CYVORA will not send a request that cannot fit."
            )
        while True:
            async with self._guard():
                self._refill()
                if self._tokens >= weight:
                    self._tokens -= weight
                    return
                wait = (weight - self._tokens) / self.rate
            await self._sleeper(wait)

    def _guard(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._updated)
        self._updated = now
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
