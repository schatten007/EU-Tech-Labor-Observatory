"""robots.txt gate and pacing helpers (SCRAPERS.md Golden rules 1-2).

The charter floor is one request per second per host, whatever robots.txt
says. :class:`PacingGate` enforces that floor; :class:`RobotsRule` parses a
fetched robots.txt (an absent file means nothing is disallowed).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Final, cast
from urllib.robotparser import RobotFileParser

MIN_PACING_SECONDS: Final = 1.0

DEFAULT_USER_AGENT = "EU-Tech-Labour-Observatory/0.1"


class RobotsRule:
    """Parsed robots.txt contract; an absent file allows everything.

    ``urllib.robotparser`` disallows until a file is read, so the absent-file
    case is short-circuited to allow-all instead of "unknown".
    """

    def __init__(self, robots_text: str | None = None) -> None:
        self._allow_all = robots_text is None
        self._parser = RobotFileParser()
        if robots_text:
            self._parser.parse(robots_text.splitlines())

    def can_fetch(self, url: str, user_agent: str = DEFAULT_USER_AGENT) -> bool:
        """True when robots.txt permits fetching ``url`` for ``user_agent``."""
        if self._allow_all:
            return True
        return self._parser.can_fetch(user_agent, url)

    def crawl_delay(self, user_agent: str = DEFAULT_USER_AGENT) -> float | None:
        """The Crawl-Delay directive for ``user_agent``, or None when absent."""
        if self._allow_all:
            return None
        value = cast(float | None, self._parser.crawl_delay(user_agent))
        if value is None:
            return None
        return max(0.0, value)


class PacingGate:
    """Ensures at least ``min_interval`` seconds between requests to a host."""

    def __init__(
        self,
        min_interval: float = MIN_PACING_SECONDS,
        *,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._min_interval = min_interval
        self._sleeper = sleeper or asyncio.sleep
        self._last: float | None = None

    async def wait(self, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        """Block until the pacing interval since the previous call has elapsed."""
        now = monotonic()
        wait_for = 0.0
        if self._last is not None:
            wait_for = max(0.0, self._last + self._min_interval - now)
        if wait_for:
            await self._sleeper(wait_for)
            now = monotonic()
        self._last = now
