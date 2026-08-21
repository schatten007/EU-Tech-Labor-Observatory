"""Retry/backoff decorator for flaky APIs (SCRAPERS.md Golden rule 2).

Retries ``httpx.TransportError`` failures and retryable status codes (429/5xx/
202) with exponential backoff plus jitter, honoring ``Retry-After``. A sweep
deadline aborts with :class:`RetryExhausted` instead of hammering the host.
"""

from __future__ import annotations

import asyncio
import functools
import random
import time
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

import httpx
from pydantic import BaseModel, Field

P = ParamSpec("P")
T = TypeVar("T")

DEFAULT_RETRY_STATUSES: frozenset[int] = frozenset({202, 429, 500, 502, 503, 504})


class RetryPolicy(BaseModel):
    """Backoff configuration shared by every source collector."""

    max_attempts: int = Field(default=4, ge=1)
    base_delay: float = Field(default=1.0, ge=0)
    max_delay: float = Field(default=60.0, ge=0)
    retry_statuses: frozenset[int] = Field(default_factory=lambda: DEFAULT_RETRY_STATUSES)
    deadline_s: float | None = Field(default=None, ge=0)
    jitter: float = Field(default=0.5, ge=0, le=1)


class RetryExhausted(RuntimeError):
    """Raised when the retry deadline expires before a request succeeds."""


async def _default_sleeper(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _delay(policy: RetryPolicy, attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return retry_after
    exponential = policy.base_delay * float(1 << max(0, attempt - 1))
    return min(policy.max_delay, exponential)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Parse the ``Retry-After`` header as whole seconds (RFC 7231 delay form)."""
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


async def _wait(
    policy: RetryPolicy,
    delay: float,
    started: float,
    *,
    sleeper: Callable[[float], Awaitable[None]],
    monotonic: Callable[[], float],
    random_value: Callable[[], float],
) -> None:
    if policy.deadline_s is not None and monotonic() - started + delay >= policy.deadline_s:
        raise RetryExhausted(f"retry deadline of {policy.deadline_s}s exceeded")
    jittered = delay * (1.0 + policy.jitter * random_value())
    await sleeper(jittered)


def with_backoff(
    policy: RetryPolicy,
    *,
    sleeper: Callable[[float], Awaitable[None]] = _default_sleeper,
    random_value: Callable[[], float] = random.random,
    monotonic: Callable[[], float] = time.monotonic,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorate an async call so transient failures are retried with backoff.

    Functions returning :class:`httpx.Response` are additionally retried on
    ``policy.retry_statuses``. Any other return type is passed through after a
    single call.
    """

    def decorate(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            started = monotonic()
            attempt = 0
            while True:
                attempt += 1
                try:
                    result = await func(*args, **kwargs)
                except httpx.TransportError:
                    if attempt >= policy.max_attempts:
                        raise
                    await _wait(
                        policy,
                        _delay(policy, attempt, None),
                        started,
                        sleeper=sleeper,
                        monotonic=monotonic,
                        random_value=random_value,
                    )
                    continue
                if not isinstance(result, httpx.Response):
                    return result
                if result.status_code not in policy.retry_statuses:
                    return result
                if attempt >= policy.max_attempts:
                    return result
                await _wait(
                    policy,
                    _delay(policy, attempt, _retry_after_seconds(result)),
                    started,
                    sleeper=sleeper,
                    monotonic=monotonic,
                    random_value=random_value,
                )

        return wrapper

    return decorate
