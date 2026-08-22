"""Unit tests for the AdzunaCollector (Increment 3) with a mocked keyed API.

Covers pagination, normalization onto the SAFE_FIELDS allowlist, PII isolation,
429 retry/backoff honoring Retry-After, the CountryAdapter config (DE vs NL
differ only by config), segment-based dedupe, and date/edge cases.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from scrapers.adzuna import (
    ADZUNA_ADAPTERS,
    ADZUNA_API_BASE,
    ADZUNA_DE,
    ADZUNA_NL,
    AdzunaCollector,
    adzuna_credentials,
    parse_adzuna_datetime,
)
from scrapers.base import NormalizedRecord
from scrapers.retry import RetryPolicy

KEY = b"test-only-key-with-at-least-32-bytes"
APP_ID = "test-app-id"
APP_KEY = "test-app-key"

DE_URL = f"{ADZUNA_API_BASE}/de/search/1"
NL_URL = f"{ADZUNA_API_BASE}/nl/search/1"


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def job(
    job_id: str,
    *,
    created: str = "2026-08-01T09:30:00Z",
    category_tag: str = "it-jobs",
) -> dict[str, Any]:
    """One search result carrying PII/free text that must never reach the allowlist."""
    return {
        "__CLASS__": "Adzuna::API::Response::Job",
        "id": job_id,
        "title": "Private Job Title",
        "description": "Very long private description with a phone +49 170 123456 and "
        "email private.person@example.com",
        "created": created,
        "category": {
            "__CLASS__": "Adzuna::API::Response::Category",
            "label": "IT Jobs",
            "tag": category_tag,
        },
        "company": {
            "__CLASS__": "Adzuna::API::Response::Company",
            "display_name": "Private Employer GmbH",
        },
        "location": {
            "__CLASS__": "Adzuna::API::Response::Location",
            "area": ["Germany", "Bavaria", "Munich"],
            "display_name": "Munich, Bavaria",
        },
        "latitude": 48.137,
        "longitude": 11.575,
        "salary_min": 60000,
        "salary_max": 80000,
        "salary_is_predicted": 0,
        "contract_type": "permanent",
        "contract_time": "full_time",
        "redirect_url": "https://www.adzuna.de/jobs/land/ad/1234567?v=abcdef&utm_medium=api",
    }


def search_response(count: int, results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "__CLASS__": "Adzuna::API::Response::JobSearchResults",
        "count": count,
        "results": results,
    }


def make_collector(
    *,
    adapter: Any = ADZUNA_DE,
    max_pages: int | None = None,
    policy: RetryPolicy | None = None,
    **kwargs: Any,
) -> AdzunaCollector:
    return AdzunaCollector(
        scope_id=adapter.scope_id,
        sweep_id="20260822T000000Z",
        observed_at=datetime(2026, 8, 22, tzinfo=UTC),
        hmac_key=KEY,
        adapter=adapter,
        app_id=APP_ID,
        app_key=APP_KEY,
        pacing_interval=0.0,
        max_pages=max_pages,
        policy=policy,
        **kwargs,
    )


def test_credentials_loaded_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADZUNA_APP_ID", "env-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "env-key")
    assert adzuna_credentials() == ("env-id", "env-key")


def test_credentials_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    # .env may carry real keys; force the dotenv reader to report none.
    monkeypatch.setattr("scrapers.adzuna.read_dotenv_value", lambda _name: None)
    with pytest.raises(RuntimeError, match="ADZUNA_APP_ID and ADZUNA_APP_KEY"):
        adzuna_credentials()


def test_paginates_and_normalizes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.path.rsplit("/", 1)[1])
        assert request.url.params["app_id"] == APP_ID
        assert request.url.params["app_key"] == APP_KEY
        assert request.url.params["results_per_page"] == "50"
        offset = (page - 1) * 50
        return httpx.Response(
            200,
            json=search_response(100, [job(f"native-{offset + i}") for i in range(50)]),
        )

    with respx.mock:
        respx.get(url__regex=r"https://api\.adzuna\.com/v1/api/jobs/de/search/\d+").mock(
            side_effect=handler
        )

        async def collect() -> tuple[list[NormalizedRecord], AdzunaCollector]:
            collector = make_collector()
            async with collector:
                records = [record async for record in collector.collect()]
                return records, collector

        records, collector = run(collect())

    assert len(records) == 100
    assert collector.completed_pages == 2
    assert collector.total_pages == 2  # ceil(100 / 50) == 2
    assert collector.advertised_count == 100
    assert collector.total_elements == 100
    assert all(len(record.source_id) == 64 for record in records)
    assert all(record.country == "DE" for record in records)
    assert all(record.lang == "de" for record in records)
    assert all(record.source_language == "de" for record in records)
    assert all(record.number_of_vacancies == 1 for record in records)
    assert all(
        record.first_published == datetime(2026, 8, 1, 9, 30, tzinfo=UTC) for record in records
    )
    assert all(record.removed_at is None for record in records)
    assert all(record.last_modified is None for record in records)
    assert all(record.region_mapping_status == "not_present" for record in records)
    assert all(record.occupation_mapping_status == "not_present" for record in records)
    assert all(record.nuts_version == "NUTS-2024" for record in records)
    assert all(record.source == "adzuna" for record in records)


def test_pii_never_reaches_output() -> None:
    item = job("native-1")
    with respx.mock:
        respx.get(DE_URL).mock(return_value=httpx.Response(200, json=search_response(1, [item])))

        async def collect() -> list[NormalizedRecord]:
            collector = make_collector()
            async with collector:
                return [record async for record in collector.collect()]

        records = run(collect())

    dumped = json.dumps(records[0].model_dump_ndjson(), ensure_ascii=False)
    assert "Private Job Title" not in dumped
    assert "private.person@example.com" not in dumped
    assert "49 170 123456" not in dumped
    assert "Private Employer" not in dumped
    assert "Munich" not in dumped
    assert "adzuna.de/jobs/land" not in dumped
    assert "Very long private description" not in dumped
    # The allowlist itself is the only key set.
    assert set(records[0].model_dump()) == {
        "source",
        "source_id",
        "scope_id",
        "sweep_id",
        "observed_at",
        "first_published",
        "last_modified",
        "removed_at",
        "nuts_code",
        "nuts_label",
        "region_mapping_status",
        "region_mapping_method",
        "nuts_version",
        "country",
        "esco_occupation_uri",
        "esco_occupation_label",
        "occupation_mapping_status",
        "occupation_mapping_confidence",
        "occupation_mapping_method",
        "source_language",
        "jobtech_taxonomy_version",
        "esco_version",
        "skill_mappings",
        "lang",
        "number_of_vacancies",
    }


def test_retries_429_honoring_retry_after() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "throttled"})
        return httpx.Response(200, json=search_response(1, [job("native-1")]))

    with respx.mock:
        respx.get(DE_URL).mock(side_effect=handler)
        policy = RetryPolicy(max_attempts=3, base_delay=0.01, jitter=0.0)

        async def collect() -> list[NormalizedRecord]:
            collector = make_collector(policy=policy)
            async with collector:
                return [record async for record in collector.collect()]

        records = run(collect())

    assert calls == 2
    assert len(records) == 1


def test_nl_runs_same_class_config_only() -> None:
    """NL differs from DE only by CountryAdapter config, not by class/behaviour."""
    assert ADZUNA_NL.country_code == "nl"
    assert ADZUNA_NL.expected_country == "NL"
    assert ADZUNA_NL.locale == "nl_NL"
    assert ADZUNA_NL.language == "nl"
    assert ADZUNA_NL.scope_id == "nl-all-active"
    assert ADZUNA_NL.source_version == ADZUNA_DE.source_version
    assert ADZUNA_ADAPTERS["nl"] is ADZUNA_NL
    assert ADZUNA_ADAPTERS["de"] is ADZUNA_DE

    with respx.mock:
        respx.get(NL_URL).mock(
            return_value=httpx.Response(200, json=search_response(1, [job("nl-1")]))
        )

        async def collect() -> list[NormalizedRecord]:
            collector = make_collector(adapter=ADZUNA_NL)
            async with collector:
                return [record async for record in collector.collect()]

        records = run(collect())

    assert records[0].country == "NL"
    assert records[0].lang == "nl"
    assert records[0].source_language == "nl"
    assert records[0].scope_id == "nl-all-active"


def test_dedupes_across_segments() -> None:
    """The same native id across overlapping segments is written once."""
    with respx.mock:
        respx.get(url__regex=r"https://api\.adzuna\.com/v1/api/jobs/de/search/\d+").mock(
            side_effect=lambda request: httpx.Response(
                200,
                json=search_response(2, [job("shared-1"), job("segment-2")]),
            )
        )

        async def collect() -> list[NormalizedRecord]:
            collector = make_collector(
                segments=[{"category": "it-jobs"}, {"category": "sales-jobs"}]
            )
            async with collector:
                return [record async for record in collector.collect()]

        records = run(collect())

    source_ids = [record.source_id for record in records]
    assert len(source_ids) == 2
    assert len(set(source_ids)) == 2  # deduped across segments


def test_segment_by_category_fetches_categories_then_paginates() -> None:
    with respx.mock:
        respx.get(f"{ADZUNA_API_BASE}/de/categories").mock(
            return_value=httpx.Response(
                200,
                json={
                    "__CLASS__": "Adzuna::API::Response::Categories",
                    "results": [{"label": "IT Jobs", "tag": "it-jobs"}],
                },
            )
        )
        respx.get(f"{ADZUNA_API_BASE}/de/search/1").mock(
            return_value=httpx.Response(200, json=search_response(1, [job("cat-1")]))
        )

        async def collect() -> list[NormalizedRecord]:
            collector = make_collector(segment_by_category=True)
            async with collector:
                return [record async for record in collector.collect()]

        records = run(collect())

    assert len(records) == 1


def test_max_pages_budget_stops_early() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.path.rsplit("/", 1)[1])
        offset = (page - 1) * 50
        return httpx.Response(
            200,
            json=search_response(1000, [job(f"native-{offset + i}") for i in range(50)]),
        )

    with respx.mock:
        respx.get(url__regex=r"https://api\.adzuna\.com/v1/api/jobs/de/search/\d+").mock(
            side_effect=handler
        )

        async def collect() -> tuple[list[NormalizedRecord], AdzunaCollector]:
            collector = make_collector(max_pages=2)
            async with collector:
                records = [record async for record in collector.collect()]
                return records, collector

        records, collector = run(collect())

    assert len(records) == 100
    assert collector.completed_pages == 2
    assert collector.total_pages == 2
    assert collector.advertised_count == 1000
    assert collector.total_elements == 100


def test_empty_results_page_stops_pagination() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.path.rsplit("/", 1)[1])
        if page == 1:
            return httpx.Response(200, json=search_response(5, [job("native-1")]))
        return httpx.Response(200, json=search_response(5, []))

    with respx.mock:
        respx.get(url__regex=r"https://api\.adzuna\.com/v1/api/jobs/de/search/\d+").mock(
            side_effect=handler
        )

        async def collect() -> list[NormalizedRecord]:
            collector = make_collector()
            async with collector:
                return [record async for record in collector.collect()]

        records = run(collect())

    assert len(records) == 1
    assert records[0].first_published == datetime(2026, 8, 1, 9, 30, tzinfo=UTC)


def test_missing_id_fails_loudly() -> None:
    bad = job("native-1")
    del bad["id"]
    with respx.mock:
        respx.get(DE_URL).mock(return_value=httpx.Response(200, json=search_response(1, [bad])))

        async def collect() -> list[NormalizedRecord]:
            collector = make_collector()
            async with collector:
                return [record async for record in collector.collect()]

        with pytest.raises(ValueError):
            run(collect())


def test_integer_id_coerced_to_string() -> None:
    """Probed live: DE returns string ids, NL returns integers."""
    int_item = job("99999")
    int_item["id"] = 1534937649  # NL-style integer id
    with respx.mock:
        respx.get(NL_URL).mock(
            return_value=httpx.Response(200, json=search_response(1, [int_item]))
        )

        async def collect() -> list[NormalizedRecord]:
            collector = make_collector(adapter=ADZUNA_NL)
            async with collector:
                return [record async for record in collector.collect()]

        records = run(collect())

    assert len(records) == 1
    assert len(records[0].source_id) == 64
    assert records[0].country == "NL"


def test_parse_adzuna_datetime() -> None:
    assert parse_adzuna_datetime("2026-08-01T09:30:00Z") == datetime(2026, 8, 1, 9, 30, tzinfo=UTC)
    assert parse_adzuna_datetime(None) is None
    assert parse_adzuna_datetime("garbage") is None


def test_native_id_not_in_output_and_source_ids_unique() -> None:
    items = [job("native-1"), job("native-2"), job("native-3")]
    with respx.mock:
        respx.get(DE_URL).mock(return_value=httpx.Response(200, json=search_response(3, items)))

        async def collect() -> list[NormalizedRecord]:
            collector = make_collector()
            async with collector:
                return [record async for record in collector.collect()]

        records = run(collect())

    dumped = json.dumps([record.model_dump_ndjson() for record in records], ensure_ascii=False)
    assert "native-1" not in dumped
    assert "native-2" not in dumped
    assert len({record.source_id for record in records}) == 3
    assert all(len(record.source_id) == 64 for record in records)
