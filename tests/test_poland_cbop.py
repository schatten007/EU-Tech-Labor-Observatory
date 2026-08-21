"""Unit tests for the PolandCollector (Task 6) with a mocked CBOP search API."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import respx

from scrapers.base import NormalizedRecord
from scrapers.poland_cbop import CBOPCollector, PolandCollector, parse_pl_date
from scrapers.retry import RetryPolicy

KEY = b"test-only-key-with-at-least-32-bytes"
URL = "https://oferty.praca.gov.pl/portal-api/v3/oferta/wyszukiwanie"


def offer(offer_id: str, *, status: str = "A", published: str = "19.08.2026") -> dict[str, Any]:
    return {
        "id": offer_id,
        "status": status,
        "email": "private@example.com",
        "telefon": "123 456 789",
        "osobaDoKontaktu": "Private Person",
        "pracodawca": "Acme Sp. z o.o.",
        "pracodawcaAdres": "Warszawa, mazowieckie",
        "stanowisko": "Private title",
        "wymagania": "Private requirements",
        "zakresObowiazkow": "Private duties",
        "dataDodaniaCbop": published,
        "dataWaznOd": published,
        "dataWaznDo": "18.09.2026",
        "miejscowoscId": "0939473",
        "miejscowoscNazwa": None,
        "typOfertyEnum": "OFERTA_PRACY",
        "liczbaWolnychMiejscDlaNiepeln": 0,
    }


def page(
    number: int,
    total_elements: int,
    total_pages: int,
    last: bool,
    content: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": 200,
        "msg": "OK",
        "payload": {
            "ofertyPracyPage": {
                "number": number,
                "size": 100,
                "totalElements": total_elements,
                "totalPages": total_pages,
                "last": last,
                "content": content,
            },
            "iloscMiejscPracy": 3,
        },
    }


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_collect_paginates_and_normalizes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page_num = int(request.url.params["page"])
        if page_num == 0:
            return httpx.Response(
                200, json=page(0, 3, 2, False, [offer("native-1"), offer("native-2")])
            )
        return httpx.Response(200, json=page(1, 3, 2, True, [offer("native-3")]))

    with respx.mock:
        respx.post(URL).mock(side_effect=handler)

        async def collect() -> list[NormalizedRecord]:
            collector = PolandCollector(
                scope_id="pl-all-active",
                sweep_id="20260821T000000Z",
                observed_at=datetime(2026, 8, 21, tzinfo=UTC),
                hmac_key=KEY,
                pacing_interval=0.0,
            )
            async with collector:
                return [record async for record in collector.collect()]

        records = run(collect())

    assert len(records) == 3
    assert all(len(record.source_id) == 64 for record in records)
    assert all(record.country == "PL" for record in records)
    assert all(record.number_of_vacancies == 1 for record in records)
    assert all(record.first_published == datetime(2026, 8, 19, tzinfo=UTC) for record in records)
    # PII and free text never reach the allowlist.
    assert all("pracodawca" not in record.model_dump() for record in records)
    assert all("email" not in record.model_dump() for record in records)
    assert all("telefon" not in record.model_dump() for record in records)


def test_non_active_offer_is_stamped_removed() -> None:
    with respx.mock:
        respx.post(URL).mock(
            return_value=httpx.Response(200, json=page(0, 1, 1, True, [offer("gone", status="U")]))
        )

        async def collect() -> list[NormalizedRecord]:
            collector = PolandCollector(
                scope_id="pl-all-active",
                sweep_id="w",
                observed_at=datetime(2026, 8, 21, tzinfo=UTC),
                hmac_key=KEY,
                pacing_interval=0.0,
            )
            async with collector:
                return [record async for record in collector.collect()]

        records = run(collect())

    assert records[0].removed_at == datetime(2026, 8, 21, tzinfo=UTC)
    assert records[0].first_published == datetime(2026, 8, 19, tzinfo=UTC)


def test_collector_retries_transient_failure() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=page(0, 1, 1, True, [offer("ok")]))

    with respx.mock:
        respx.post(URL).mock(side_effect=handler)
        policy = RetryPolicy(max_attempts=3, base_delay=0.01, jitter=0.0)

        async def collect() -> list[NormalizedRecord]:
            collector = PolandCollector(
                scope_id="s",
                sweep_id="w",
                observed_at=datetime(2026, 8, 21, tzinfo=UTC),
                hmac_key=KEY,
                pacing_interval=0.0,
                policy=policy,
            )
            async with collector:
                return [record async for record in collector.collect()]

        records = run(collect())

    assert calls == 2
    assert len(records) == 1


def test_parse_pl_date() -> None:
    assert parse_pl_date("19.08.2026") == datetime(2026, 8, 19, tzinfo=UTC)
    assert parse_pl_date(None) is None
    assert parse_pl_date("garbage") is None


def test_cbop_collector_alias() -> None:
    assert CBOPCollector is PolandCollector
