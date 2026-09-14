"""Small in-process request limiter used by the API middleware.

The limiter is deliberately dependency-free for local/test deployments.  A
multi-worker deployment should place the same counters in Redis, but requests
are still bounded when running a single process.
"""
from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic


class RateLimiter:
    def __init__(self, per_minute: int, per_hour: int):
        self.per_minute = max(0, per_minute)
        self.per_hour = max(0, per_hour)
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> tuple[bool, int]:
        now = monotonic()
        events = self._events[key]
        while events and now - events[0] >= 3600:
            events.popleft()

        minute_count = sum(1 for event in events if now - event < 60)
        hour_count = len(events)
        if (self.per_minute and minute_count >= self.per_minute) or (
            self.per_hour and hour_count >= self.per_hour
        ):
            retry_after = 60 if minute_count >= self.per_minute else 3600
            return False, retry_after

        events.append(now)
        # Avoid unbounded key growth when a client sends one request and never
        # returns.  Old keys are cheap to discard opportunistically.
        if len(self._events) > 10000:
            stale = [name for name, values in self._events.items() if not values]
            for name in stale[:1000]:
                self._events.pop(name, None)
        return True, 0
