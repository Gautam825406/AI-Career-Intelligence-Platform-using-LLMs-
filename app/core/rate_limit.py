"""Minimal in-memory sliding-window rate limiter.

This is intentionally simple: per-process, per-client-IP, fixed window.
It is enough to satisfy "429 when the service or provider rate limit is
reached" for a single-instance deployment. For multi-instance deployments,
swap this out for a shared store (Redis, etc.) behind the same interface.
"""

import time
from collections import defaultdict, deque


class InMemoryRateLimiter:
    def __init__(self, max_requests: int, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, client_key: str) -> bool:
        """Return True if the request is allowed, False if it should be rejected."""
        now = time.monotonic()
        window = self._hits[client_key]

        while window and now - window[0] > self.window_seconds:
            window.popleft()

        if len(window) >= self.max_requests:
            return False

        window.append(now)
        return True
