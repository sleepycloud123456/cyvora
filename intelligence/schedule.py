"""Intervals for a radar loop the operator starts.

A failed or rate-limited cycle waits longer. The wait never drops below the
configured interval, and it never starts by itself.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from intelligence.cycle import CycleResult


def next_delay_seconds(base_seconds: int, result: CycleResult) -> int:
    """Return the wait before another cycle."""

    stretched = result.rate_limit_hits > 0 or result.status in {"failed", "partial"}
    if not stretched:
        return base_seconds
    return min(base_seconds * 2, 900)


class RadarScheduler:
    """Run a cycle callback until stopped or ``max_cycles`` is reached."""

    def __init__(
        self,
        runner: Callable[[], Awaitable[CycleResult]],
        *,
        interval_seconds: int,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._runner = runner
        self._interval = interval_seconds
        self._sleeper = sleeper or asyncio.sleep
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self, *, max_cycles: int) -> list[CycleResult]:
        results: list[CycleResult] = []
        for index in range(max_cycles):
            if self._stop.is_set():
                break
            results.append(await self._runner())
            if index + 1 == max_cycles or self._stop.is_set():
                break
            delay = next_delay_seconds(self._interval, results[-1])
            await self._sleeper(delay)
        return results
