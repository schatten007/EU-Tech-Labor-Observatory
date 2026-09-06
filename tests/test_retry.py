"""Unit tests for the retry/backoff decorator (Task 3)."""

import asyncio
from typing import Any

import httpx
import pytest

from scrapers.retry import RetryExhausted, RetryPolicy, with_backoff


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_retries_retryable_status_then_succeeds() -> None:
    calls = 0
    sleeps: list[float] = []

    async def fake_sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    async def do() -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    wrapped = with_backoff(
        RetryPolicy(max_attempts=3, base_delay=1.0, jitter=0.0),
        sleeper=fake_sleeper,
        random_value=lambda: 0.0,
        monotonic=lambda: 0.0,
    )(do)

    result = run(wrapped())
    assert result.status_code == 200
    assert calls == 2
    assert sleeps == [1.0]


def test_honors_retry_after_header() -> None:
    calls = 0
    sleeps: list[float] = []

    async def fake_sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    async def do() -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200)

    wrapped = with_backoff(
        RetryPolicy(max_attempts=2, jitter=0.0),
        sleeper=fake_sleeper,
        random_value=lambda: 0.0,
        monotonic=lambda: 0.0,
    )(do)

    run(wrapped())
    assert calls == 2
    assert sleeps == [3.0]


def test_does_not_retry_client_error() -> None:
    calls = 0

    async def do() -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400)

    wrapped = with_backoff(
        RetryPolicy(max_attempts=4), random_value=lambda: 0.0, monotonic=lambda: 0.0
    )(do)

    result = run(wrapped())
    assert result.status_code == 400
    assert calls == 1


def test_retries_transport_error_then_succeeds() -> None:
    calls = 0
    sleeps: list[float] = []

    async def fake_sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    async def do() -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("temporary")
        return httpx.Response(200)

    wrapped = with_backoff(
        RetryPolicy(max_attempts=2, jitter=0.0),
        sleeper=fake_sleeper,
        random_value=lambda: 0.0,
        monotonic=lambda: 0.0,
    )(do)

    run(wrapped())
    assert calls == 2
    assert sleeps == [1.0]


def test_exhausts_attempts_on_transport_error() -> None:
    calls = 0

    async def do() -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("down")

    wrapped = with_backoff(
        RetryPolicy(max_attempts=2, jitter=0.0),
        sleeper=lambda seconds: asyncio.sleep(seconds),
        random_value=lambda: 0.0,
        monotonic=lambda: 0.0,
    )(do)

    with pytest.raises(httpx.ConnectError):
        run(wrapped())
    assert calls == 2


def test_deadline_aborts_with_retry_exhausted() -> None:
    async def do() -> httpx.Response:
        raise httpx.ConnectError("down")

    wrapped = with_backoff(
        RetryPolicy(max_attempts=5, base_delay=10.0, deadline_s=5.0, jitter=0.0),
        sleeper=lambda seconds: asyncio.sleep(seconds),
        random_value=lambda: 0.0,
        monotonic=lambda: 0.0,
    )(do)

    with pytest.raises(RetryExhausted):
        run(wrapped())


def test_non_response_result_passes_through_once() -> None:
    calls = 0

    async def do() -> int:
        nonlocal calls
        calls += 1
        return 42

    wrapped = with_backoff(
        RetryPolicy(max_attempts=4), random_value=lambda: 0.0, monotonic=lambda: 0.0
    )(do)

    assert run(wrapped()) == 42
    assert calls == 1
