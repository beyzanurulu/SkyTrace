"""Rate-limited model calls for the evaluation scripts (free cloud tiers)."""

from __future__ import annotations

import time
from typing import Any, Final

from skytrace.agent.graph import Complete, Message, is_capacity_error

RATE_LIMIT_RETRIES: Final = 6


class Throttled:
    """A Complete that keeps to ``rpm`` calls per minute and retries rate limits."""

    def __init__(self, complete: Complete, rpm: float) -> None:
        self.complete = complete
        self.interval = 60.0 / rpm
        self.last = 0.0
        self.waited = 0.0  # seconds slept, subtracted from the latency

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)
        self.waited += seconds

    def __call__(self, messages: list[Message], tools: list[dict[str, Any]]) -> Message:
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            gap = self.last + self.interval - time.monotonic()
            if gap > 0:
                self._sleep(gap)
            self.last = time.monotonic()
            try:
                return self.complete(messages, tools)
            except Exception as exc:
                if attempt == RATE_LIMIT_RETRIES or not is_capacity_error(exc):
                    raise
                self._sleep(min(60.0, 10.0 * 2**attempt))
        raise AssertionError("unreachable")
