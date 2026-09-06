"""Unit tests for robots.txt parsing and pacing (Task 3)."""

import asyncio
from typing import Any

import pytest

from scrapers.robots import PacingGate, RobotsRule


def test_absent_robots_allows_everything() -> None:
    rule = RobotsRule()
    assert rule.can_fetch("https://oferty.praca.gov.pl/portal-api/v3/oferta")
    assert rule.crawl_delay() is None


def test_robots_parse_honors_disallow_and_delay() -> None:
    text = "User-agent: *\nDisallow: /integration/\nCrawl-delay: 2"
    rule = RobotsRule(text)
    assert not rule.can_fetch("https://oferty.praca.gov.pl/integration/services/oferta")
    assert rule.can_fetch("https://oferty.praca.gov.pl/portal-api/v3/oferta")
    assert rule.crawl_delay() == 2.0


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_pacing_gate_enforces_min_interval() -> None:
    sleeps: list[float] = []

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    clock = FakeClock()
    gate = PacingGate(min_interval=1.0, sleeper=sleeper)

    async def drive() -> None:
        await gate.wait(monotonic=clock)
        clock.advance(0.2)
        await gate.wait(monotonic=clock)
        clock.advance(0.2)
        await gate.wait(monotonic=clock)

    run(drive())
    assert sleeps == pytest.approx([0.8, 0.8])
