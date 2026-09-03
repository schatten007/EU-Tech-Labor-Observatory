"""Unit tests for FinlandTMTCollector (Increment 7) against mocked P67 streams.

Covers credential loading from the environment and ``.env``, the Kipa
subscription-key header, the bearer-401 refresh-once-and-replay path, NDJSON line
parsing (including malformed lines and the loud schema-drift guard), the
watermark that stands in for the cursor the API does not have, the ``--max-rows``
budget, ESCO occupation and skill extraction across every FINESCO namespace,
region resolution from KUNTA and MAAKUNTA codes, PII isolation on both the
``NormalizedRecord`` **and** the intermediate ``RawRecord``, ``429`` backoff
honoring ``Retry-After``, the robots gate and the IP-allowlist transport error.

Fixtures are hand-written synthetic payloads modelled on the live OpenAPI
description; no real employer, person or vacancy text is stored in the repository.
"""

import asyncio
import json
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from scrapers.base import NormalizedRecord, RawRecord
from scrapers.finland_tmt import (
    TMT_KIPA_BASE,
    TMT_REFERENCE_FILE,
    TMT_STATUS_ARCHIVED,
    FinlandCrosswalk,
    FinlandTMTCollector,
    StreamWatermark,
    crosswalk_reference_hashes,
    load_watermark,
    normalize_kunta_code,
    normalize_maakunta_code,
    parse_tmt_datetime,
    resolve_occupation,
    resolve_skills,
    save_watermark,
    tmt_credentials,
)
from scrapers.retry import RetryPolicy
from scrapers.robots import RobotsDisallowedError

KEY = b"test-only-key-with-at-least-32-bytes"
SUBSCRIPTION_KEY = "kipa-subscription-key-for-tests"

SEARCH_URL = f"{TMT_KIPA_BASE}/kipa/p67/v2/jobpostings"
ROBOTS_URL = f"{TMT_KIPA_BASE}/robots.txt"

OCCUPATION_URI = "http://data.europa.eu/esco/occupation/0b15375e-dfdd-4047-9efb-096e0aaee7d2"
OCCUPATION_URI_2 = "http://data.europa.eu/esco/occupation/4fa660b3-ab97-4a99-ad73-ce3c2612f2c3"
ISCO_GROUP_URI = "http://data.europa.eu/esco/isco/C2511"
NATIONAL_URI = "http://data.tyomarkkinatori.fi/esco/occupation/finnish-extension-1"
SKILL_URI = "http://data.europa.eu/esco/skill/4c016b68-4116-468c-9dc6-42710c239e4a"
SKILL_URI_2 = "http://data.europa.eu/esco/skill/b633eb55-8f1f-4ae6-ab4c-2022ffe2cb7f"
ISCED_F_URI = "http://data.europa.eu/esco/isced-f/0611"

HEADER = "source_type,source_code,nuts_code,nuts_label,source_url,source_version\n"
ROWS = (
    "kunta,091,FI1B1,Helsinki-Uusimaa,https://example.invalid/kunta,2026-08-23\n"
    "kunta,853,FI1C1,Varsinais-Suomi,https://example.invalid/kunta,2026-08-23\n"
    "kunta,683,FI1D7,Lappi,https://example.invalid/kunta,2026-08-23\n"
    "kunta,478,FI200,Åland,https://example.invalid/kunta,2026-08-23\n"
    "kunta,049,FI1B1,Helsinki-Uusimaa,https://example.invalid/kunta,2026-08-23\n"
    "maakunta,01,FI1B1,Helsinki-Uusimaa,https://example.invalid/maakunta,2026-08-23\n"
    "maakunta,19,FI1D7,Lappi,https://example.invalid/maakunta,2026-08-23\n"
    "maakunta-ambiguous,02,,,https://example.invalid/maakunta,2026-08-23\n"
)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


@pytest.fixture
def reference_dir(tmp_path: Path) -> Path:
    (tmp_path / TMT_REFERENCE_FILE).write_text(HEADER + ROWS, encoding="utf-8")
    return tmp_path


def posting(
    external_id: str,
    *,
    municipalities: list[str] | None = None,
    regions: list[str] | None = None,
    occupations: list[str] | None = None,
    main_occupation: str | None = OCCUPATION_URI,
    skills: list[str] | None = None,
    languages: list[str] | None = None,
    published: str | None = "2026-08-20T08:15:00.000000",
    created: str = "2026-08-19T07:00:00.000000",
    last_modified: str = "2026-08-21T09:34:28.673623",
    archived: str | None = None,
    open_positions: int | None = 2,
) -> dict[str, Any]:
    """One synthetic JobPostingV2, carrying the PII the allowlist must never let through."""
    payload: dict[str, Any] = {
        "languages": languages if languages is not None else ["fi", "en"],
        "descriptionsContentType": "markdown",
        "metadata": {
            "externalId": external_id,
            "created": created,
            "lastModified": last_modified,
        },
        "client": {
            "businessId": "1234567-8",
            "company": "Private Principal Oy",
            "officeName": "Private Principal Helsinki",
            "industryCode": "62010",
        },
        "owner": {
            "employerType": "COMPANY",
            "businessId": "8765432-1",
            "company": {"fi": "Private Employer Oy"},
            "officeName": "Private Employer Tampere",
            "reference": "REQ-2026-0001",
            "householdEmployer": "Private Household Person",
        },
        "position": {
            "mainOccupation": main_occupation,
            "occupations": occupations if occupations is not None else [],
            "skills": skills if skills is not None else [SKILL_URI, SKILL_URI_2],
            "title": {"fi": "Private Job Title"},
            "jobDescription": {"fi": "Yksityinen kuvaus, yhteys privat@example.invalid."},
            "marketingDescription": {"fi": "Yksityinen markkinointiteksti."},
            "employmentRelationship": "1",
            "workTime": "1",
        },
        "location": {
            "countries": ["FI"],
            "regions": regions if regions is not None else [],
            "municipalities": municipalities if municipalities is not None else ["091"],
            "workplaceAddress": "Yksityinen katu 1",
            "workplacePostalCode": "00100",
            "workplacePostOffice": "HELSINKI",
            "workplaceName": {"fi": "Private Workplace"},
        },
        "application": {
            "expires": "2026-09-06T00:00:00.000000",
            "openPositions": open_positions,
            "helpText": {"fi": "Soita 040 123 4567."},
            "url": {"fi": "https://employer.example.invalid/apply"},
        },
        "externalLinks": [{"url": "https://employer.example.invalid", "description": "Kotisivu"}],
        "contacts": [
            {
                "firstName": "Yksityinen",
                "lastName": "Yhteyshenkilo",
                "email": "privat@example.invalid",
                "telephone": "0401234567",
            }
        ],
    }
    if published is not None:
        payload["application"]["published"] = published
    if archived is not None:
        payload["metadata"]["archived"] = archived
    return payload


def ndjson(*payloads: dict[str, Any] | str) -> str:
    """Serialize payloads as an NDJSON body (strings are inserted verbatim)."""
    lines = [
        item if isinstance(item, str) else json.dumps(item, ensure_ascii=False) for item in payloads
    ]
    return "\n".join(lines) + "\n"


def mock_robots(router: respx.Router, *, status: int = 404, text: str = "") -> respx.Route:
    headers = {"content-type": "text/plain"} if status == 200 else {}
    return router.get(ROBOTS_URL).mock(
        return_value=httpx.Response(status, text=text, headers=headers)
    )


def build(reference_dir: Path, **kwargs: Any) -> FinlandTMTCollector:
    params: dict[str, Any] = {
        "scope_id": "fi-all-active",
        "sweep_id": "20260823T000000Z",
        "observed_at": datetime(2026, 8, 23, tzinfo=UTC),
        "hmac_key": KEY,
        "subscription_key": SUBSCRIPTION_KEY,
        "reference_dir": reference_dir,
        "cursor_path": reference_dir / "state.json",
        "pacing_interval": 0.0,
        "policy": RetryPolicy(max_attempts=3, base_delay=0.0, jitter=0.0),
    }
    params.update(kwargs)
    return FinlandTMTCollector(**params)


async def collect(collector: FinlandTMTCollector) -> list[NormalizedRecord]:
    async with collector:
        return [record async for record in collector.collect()]


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def test_credentials_load_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMT_KIPA_SUBSCRIPTION_KEY", "env-key")
    monkeypatch.setenv("TMT_BEARER_TOKEN", "env.bearer.token")
    assert tmt_credentials() == ("env-key", "env.bearer.token")


def test_credentials_fall_back_to_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TMT_KIPA_SUBSCRIPTION_KEY", raising=False)
    monkeypatch.delenv("TMT_BEARER_TOKEN", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nTMT_KIPA_SUBSCRIPTION_KEY = dotenv-key \nTMT_BEARER_TOKEN=dotenv.bearer\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scrapers.sanitize.ENV_FILE", env_file)
    assert tmt_credentials() == ("dotenv-key", "dotenv.bearer")


def test_a_missing_key_raises_before_any_network_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TMT_KIPA_SUBSCRIPTION_KEY", raising=False)
    monkeypatch.setattr("scrapers.sanitize.ENV_FILE", tmp_path / "absent.env")
    with pytest.raises(RuntimeError, match="TMT_KIPA_SUBSCRIPTION_KEY is not set"):
        tmt_credentials()


def test_the_bearer_token_is_optional(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TMT_KIPA_SUBSCRIPTION_KEY", "env-key")
    monkeypatch.delenv("TMT_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("scrapers.sanitize.ENV_FILE", tmp_path / "absent.env")
    assert tmt_credentials() == ("env-key", None)


def test_the_collector_refuses_an_empty_key_or_a_short_hmac(reference_dir: Path) -> None:
    with pytest.raises(ValueError, match="KIPA-Subscription-Key"):
        build(reference_dir, subscription_key="")
    with pytest.raises(ValueError, match="hmac_key"):
        build(reference_dir, hmac_key=b"too-short")
    with pytest.raises(ValueError, match="only_status"):
        build(reference_dir, only_status="EVERYTHING")


# ---------------------------------------------------------------------------
# Stream parsing
# ---------------------------------------------------------------------------


@respx.mock
def test_the_stream_yields_one_row_per_ndjson_line_with_the_kipa_key(
    reference_dir: Path,
) -> None:
    mock_robots(respx.mock)
    route = respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson(posting("a-1"), posting("a-2"), posting("a-3")),
            headers={
                "content-type": "application/x-ndjson",
                "RateLimit-Limit": "600",
                "RateLimit-Remaining": "599",
                "RateLimit-Reset": "60",
            },
        )
    )
    collector = build(reference_dir)
    rows = run(collect(collector))

    assert len(rows) == 3
    assert collector.lines_seen == 3
    assert collector.streams_completed == 1
    assert collector.total_pages == collector.completed_pages == 1
    assert collector.total_elements == 3
    assert collector.rate_limit == {
        "RateLimit-Limit": "600",
        "RateLimit-Remaining": "599",
        "RateLimit-Reset": "60",
    }
    request = route.calls.last.request
    assert request.headers["KIPA-Subscription-Key"] == SUBSCRIPTION_KEY
    assert "Authorization" not in request.headers
    assert json.loads(request.content) == {"onlyStatus": "PUBLISHED"}


@respx.mock
def test_blank_and_malformed_lines_are_counted_and_skipped(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    body = ndjson(
        posting("a-1"),
        "   ",
        "{not json at all",
        "[1, 2, 3]",
        json.dumps({"languages": ["fi"], "metadata": {"created": "2026-08-01T00:00:00.000000"}}),
        posting("a-2"),
    )
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200, text=body, headers={"content-type": "application/x-ndjson"}
        )
    )
    collector = build(reference_dir)
    rows = run(collect(collector))

    assert len(rows) == 2
    assert collector.lines_seen == 5  # the blank line is not counted at all
    assert collector.malformed_lines == 2  # invalid JSON and a JSON array
    assert collector.rows_without_id == 1  # valid JSON, no metadata.externalId


@respx.mock
def test_a_structurally_wrong_line_fails_loudly(reference_dir: Path) -> None:
    """Noise is tolerated; schema drift is not."""
    mock_robots(respx.mock)
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson({"languages": ["fi"], "metadata": "no longer an object"}),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    with pytest.raises(Exception, match="metadata"):
        run(collect(build(reference_dir)))


@respx.mock
def test_a_stream_with_no_usable_row_refuses_to_write_an_empty_partition(
    reference_dir: Path,
) -> None:
    mock_robots(respx.mock)
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson("{broken", json.dumps({"languages": ["fi"], "metadata": {}})),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    with pytest.raises(RuntimeError, match="schema drift"):
        run(collect(build(reference_dir)))


@respx.mock
def test_an_empty_stream_is_not_an_error(reference_dir: Path) -> None:
    """Zero lines means "nothing changed", which a poll must tolerate."""
    mock_robots(respx.mock)
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(200, text="", headers={"content-type": "application/x-ndjson"})
    )
    collector = build(reference_dir)
    assert run(collect(collector)) == []
    assert collector.lines_seen == 0
    assert collector.total_elements == 0


@respx.mock
def test_duplicate_external_ids_are_dropped_on_the_hmac_source_id(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson(posting("a-1"), posting("a-1"), posting("a-2")),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    collector = build(reference_dir)
    rows = run(collect(collector))

    assert len(rows) == 2
    assert collector.duplicates_dropped == 1
    assert len({row.source_id for row in rows}) == 2


@respx.mock
def test_max_rows_truncates_the_stream_and_suppresses_the_watermark(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson(*(posting(f"a-{index}") for index in range(10))),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    collector = build(reference_dir, max_rows=4)
    rows = run(collect(collector))

    assert len(rows) == 4
    assert collector.truncated_by_budget is True
    # A truncated sample must not advance the watermark: the rest was never read.
    assert load_watermark(reference_dir / "state.json") is None


# ---------------------------------------------------------------------------
# Watermark (the cursor the API does not provide)
# ---------------------------------------------------------------------------


@respx.mock
def test_the_watermark_is_persisted_and_replayed_as_modified_from(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    route = respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson(
                posting("a-1", last_modified="2026-08-21T09:34:28.673623"),
                posting("a-2", last_modified="2026-08-22T11:00:00.000000"),
                posting("a-3", last_modified="2026-08-20T05:00:00.000000"),
            ),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    first = build(reference_dir)
    run(collect(first))
    assert first.watermark == "2026-08-22T11:00:00.000000"
    assert json.loads(route.calls[0].request.content) == {"onlyStatus": "PUBLISHED"}

    saved = load_watermark(reference_dir / "state.json")
    assert saved is not None
    assert saved.modified_from == "2026-08-22T11:00:00.000000"
    assert saved.only_status == "PUBLISHED"

    second = build(reference_dir)
    run(collect(second))
    assert second.modified_from_used == "2026-08-22T11:00:00.000000"
    assert json.loads(route.calls.last.request.content) == {
        "onlyStatus": "PUBLISHED",
        "modified": {"from": "2026-08-22T11:00:00.000000"},
    }


@respx.mock
def test_fresh_and_explicit_windows_override_the_watermark(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    route = respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson(posting("a-1")),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    save_watermark(
        StreamWatermark(modified_from="2026-01-01T00:00:00.000000", only_status="PUBLISHED"),
        reference_dir / "state.json",
    )

    run(collect(build(reference_dir, use_cursor=False)))
    assert json.loads(route.calls.last.request.content) == {"onlyStatus": "PUBLISHED"}

    run(collect(build(reference_dir, modified_from="2026-06-01T00:00:00.000000")))
    assert json.loads(route.calls.last.request.content)["modified"] == {
        "from": "2026-06-01T00:00:00.000000"
    }


@respx.mock
def test_a_published_watermark_is_not_reused_for_the_archived_set(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    route = respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson(posting("a-1", archived="2026-08-22T12:00:00.000000")),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    save_watermark(
        StreamWatermark(modified_from="2026-08-01T00:00:00.000000", only_status="PUBLISHED"),
        reference_dir / "state.json",
    )
    collector = build(reference_dir, only_status=TMT_STATUS_ARCHIVED)
    rows = run(collect(collector))

    assert json.loads(route.calls.last.request.content) == {"onlyStatus": "ARCHIVED"}
    assert collector.modified_from_used is None
    # metadata.archived is the source-reported closure timestamp.
    assert rows[0].removed_at == datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    assert collector.rows_removed == 1


def test_an_unreadable_watermark_file_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_watermark(path) is None
    assert load_watermark(tmp_path / "absent.json") is None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@respx.mock
def test_a_configured_bearer_is_sent_alongside_the_subscription_key(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    route = respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson(posting("a-1")),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    run(collect(build(reference_dir, bearer_token="first.jwt.token")))
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer first.jwt.token"
    assert request.headers["KIPA-Subscription-Key"] == SUBSCRIPTION_KEY


@respx.mock
def test_a_401_refreshes_the_bearer_once_and_replays_the_request(
    reference_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TMT_KIPA_SUBSCRIPTION_KEY", SUBSCRIPTION_KEY)
    monkeypatch.setenv("TMT_BEARER_TOKEN", "rotated.jwt.token")
    mock_robots(respx.mock)
    route = respx.post(SEARCH_URL).mock(
        side_effect=[
            httpx.Response(401, text=""),
            httpx.Response(
                200,
                text=ndjson(posting("a-1")),
                headers={"content-type": "application/x-ndjson"},
            ),
        ]
    )
    collector = build(reference_dir, bearer_token="stale.jwt.token")
    rows = run(collect(collector))

    assert len(rows) == 1
    assert collector.token_refreshes == 1
    assert route.call_count == 2
    assert route.calls[0].request.headers["Authorization"] == "Bearer stale.jwt.token"
    assert route.calls[1].request.headers["Authorization"] == "Bearer rotated.jwt.token"


@respx.mock
def test_a_401_without_a_bearer_is_raised_not_retried(reference_dir: Path) -> None:
    """With key-only auth there is nothing to refresh, so a 401 must surface."""
    mock_robots(respx.mock)
    route = respx.post(SEARCH_URL).mock(return_value=httpx.Response(401, text=""))
    collector = build(reference_dir)
    with pytest.raises(httpx.HTTPStatusError):
        run(collect(collector))
    assert route.call_count == 1
    assert collector.token_refreshes == 0


# ---------------------------------------------------------------------------
# Robots and pacing
# ---------------------------------------------------------------------------


@respx.mock
def test_an_absent_robots_file_allows_the_stream(reference_dir: Path) -> None:
    robots = mock_robots(respx.mock, status=404)
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson(posting("a-1")),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    assert len(run(collect(build(reference_dir)))) == 1
    assert robots.call_count == 1


@respx.mock
def test_a_disallowed_search_path_raises_instead_of_being_skipped(reference_dir: Path) -> None:
    mock_robots(respx.mock, status=200, text="User-agent: *\nDisallow: /kipa/\n")
    search = respx.post(SEARCH_URL).mock(return_value=httpx.Response(200, text=""))
    with pytest.raises(RobotsDisallowedError, match="robots.txt disallows"):
        run(collect(build(reference_dir)))
    assert search.call_count == 0


@respx.mock
def test_a_crawl_delay_larger_than_the_charter_floor_is_adopted(reference_dir: Path) -> None:
    mock_robots(respx.mock, status=200, text="User-agent: *\nCrawl-delay: 5\n")
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson(posting("a-1")),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    collector = build(reference_dir, pacing_interval=1.0)

    async def drive() -> float:
        async with collector:
            await collector._load_robots()
            return collector._pacer._min_interval

    assert run(drive()) == 5.0


@respx.mock
def test_a_crawl_delay_below_the_charter_floor_does_not_lower_the_pacer(
    reference_dir: Path,
) -> None:
    mock_robots(respx.mock, status=200, text="User-agent: *\nCrawl-delay: 0.2\n")

    async def drive() -> float:
        collector = build(reference_dir, pacing_interval=1.0)
        async with collector:
            await collector._load_robots()
            return collector._pacer._min_interval

    assert run(drive()) == 1.0


@respx.mock
def test_an_ip_filtered_gateway_reports_the_allowlist_precondition(reference_dir: Path) -> None:
    """The Kipa hosts drop TCP 443 for callers KEHA has not opened."""
    respx.get(ROBOTS_URL).mock(side_effect=httpx.ConnectTimeout("timed out"))
    with pytest.raises(RuntimeError, match="IP-allowlisted"):
        run(collect(build(reference_dir)))


@respx.mock
def test_a_429_is_retried_honoring_retry_after(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    route = respx.post(SEARCH_URL).mock(
        side_effect=[
            httpx.Response(429, text="slow down", headers={"Retry-After": "7"}),
            httpx.Response(
                200,
                text=ndjson(posting("a-1")),
                headers={"content-type": "application/x-ndjson"},
            ),
        ]
    )
    slept: list[float] = []

    async def sleeper(seconds: float) -> None:
        slept.append(seconds)

    collector = build(
        reference_dir,
        policy=RetryPolicy(max_attempts=3, base_delay=1.0, jitter=0.0),
        sleeper=sleeper,
    )
    rows = run(collect(collector))

    assert len(rows) == 1
    assert route.call_count == 2
    # The server's Retry-After wins over the exponential base delay.
    assert slept == [7.0]


@respx.mock
def test_a_transport_error_is_retried(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    route = respx.post(SEARCH_URL).mock(
        side_effect=[
            httpx.ConnectError("boom"),
            httpx.Response(
                200,
                text=ndjson(posting("a-1")),
                headers={"content-type": "application/x-ndjson"},
            ),
        ]
    )
    collector = build(reference_dir, policy=RetryPolicy(max_attempts=3, base_delay=0.0, jitter=0.0))
    assert len(run(collect(collector))) == 1
    assert route.call_count == 2


@respx.mock
def test_a_persistent_5xx_raises_after_the_retry_budget(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    route = respx.post(SEARCH_URL).mock(return_value=httpx.Response(503, text="unavailable"))
    collector = build(reference_dir, policy=RetryPolicy(max_attempts=2, base_delay=0.0, jitter=0.0))
    with pytest.raises(httpx.HTTPStatusError):
        run(collect(collector))
    assert route.call_count == 2


# ---------------------------------------------------------------------------
# ESCO occupation and skills
# ---------------------------------------------------------------------------


def test_occupation_resolution_covers_every_finesco_namespace() -> None:
    assert resolve_occupation(OCCUPATION_URI, []).uri == OCCUPATION_URI
    assert resolve_occupation(OCCUPATION_URI, []).status == "mapped"
    assert resolve_occupation(OCCUPATION_URI, []).method == "finesco_esco_occupation_uri"
    # No score at source, so no invented confidence.
    assert resolve_occupation(OCCUPATION_URI, []).confidence is None

    # mainOccupation wins; the array is only the fallback.
    assert resolve_occupation(OCCUPATION_URI, [OCCUPATION_URI_2]).uri == OCCUPATION_URI
    assert resolve_occupation(None, [OCCUPATION_URI_2]).uri == OCCUPATION_URI_2
    assert resolve_occupation(None, [ISCO_GROUP_URI, OCCUPATION_URI_2]).uri == OCCUPATION_URI_2

    isco = resolve_occupation(ISCO_GROUP_URI, [])
    assert (isco.uri, isco.status, isco.method) == (
        None,
        "low_confidence",
        "finesco_isco_group_uri_only",
    )
    national = resolve_occupation(NATIONAL_URI, [])
    assert (national.uri, national.status, national.method) == (
        None,
        "unmapped",
        "finesco_national_extension_uri",
    )
    junk = resolve_occupation("sairaanhoitaja", [])
    assert (junk.status, junk.method) == ("unmapped", "finesco_unrecognised_occupation_uri")
    absent = resolve_occupation(None, [])
    assert (absent.status, absent.method) == ("not_present", "not_available")
    assert resolve_occupation("   ", ["", "  "]).status == "not_present"


def test_skill_resolution_keeps_source_order_and_omits_missing_uris() -> None:
    assert resolve_skills([]) == []
    elements = resolve_skills([SKILL_URI, ISCED_F_URI, NATIONAL_URI, "Python", "", SKILL_URI_2])
    assert [element["status"] for element in elements] == [
        "mapped",
        "low_confidence",
        "unmapped",
        "unmapped",
        "mapped",
    ]
    assert elements[0]["uri"] == SKILL_URI
    assert elements[4]["uri"] == SKILL_URI_2
    # A missing URI is an absent key, never a null, so dict[str, str] holds.
    assert "uri" not in elements[1]
    assert all(isinstance(value, str) for element in elements for value in element.values())
    assert elements[0]["esco_version"] == "1.2.1"
    assert elements[0]["jobtech_taxonomy_version"] == ""
    assert elements[1]["method"] == "finesco_isced_f_uri"
    # Labels are left out: the source's labels are Finnish, this project publishes English.
    assert "label" not in elements[0]


@respx.mock
def test_occupation_and_skill_counters_track_the_sweep(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson(
                posting("a-1", main_occupation=OCCUPATION_URI, skills=[SKILL_URI, SKILL_URI_2]),
                posting("a-2", main_occupation=ISCO_GROUP_URI, skills=[]),
                posting("a-3", main_occupation=None, skills=[ISCED_F_URI]),
            ),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    collector = build(reference_dir)
    rows = run(collect(collector))

    assert collector.rows_with_esco_occupation == 1
    assert collector.rows_with_skills == 2
    assert collector.skill_elements == 3
    assert rows[0].esco_occupation_uri == OCCUPATION_URI
    assert rows[0].occupation_mapping_status == "mapped"
    assert rows[1].esco_occupation_uri is None
    assert rows[1].occupation_mapping_status == "low_confidence"
    assert rows[2].occupation_mapping_status == "not_present"
    assert rows[2].skill_mappings[0]["status"] == "low_confidence"
    # English-label field stays null on purpose (Increment 6 precedent).
    assert all(row.esco_occupation_label is None for row in rows)


# ---------------------------------------------------------------------------
# Region resolution
# ---------------------------------------------------------------------------


def test_region_resolution_prefers_the_municipality_then_the_region_code(
    reference_dir: Path,
) -> None:
    crosswalk = FinlandCrosswalk(reference_dir)

    hit = crosswalk.resolve(municipalities=["091"])
    assert (hit.nuts_code, hit.nuts_label, hit.status, hit.method) == (
        "FI1B1",
        "Helsinki-Uusimaa",
        "mapped",
        "tmt_kunta_nuts3",
    )
    # Two municipalities inside one NUTS 3 region stay mapped.
    assert crosswalk.resolve(municipalities=["091", "049"]).nuts_code == "FI1B1"
    # Two municipalities in different regions cannot have one NUTS 3 code.
    spread = crosswalk.resolve(municipalities=["091", "683"])
    assert (spread.nuts_code, spread.status, spread.method) == (
        None,
        "ambiguous",
        "tmt_kunta_multiple_nuts3",
    )
    # The municipality wins over the region code when both are present.
    assert crosswalk.resolve(municipalities=["683"], regions=["01"]).nuts_code == "FI1D7"
    # Region-only postings resolve too: a Finnish maakunta *is* a NUTS 3 region.
    region = crosswalk.resolve(regions=["19"])
    assert (region.nuts_code, region.status, region.method) == (
        "FI1D7",
        "mapped",
        "tmt_maakunta_nuts3",
    )
    assert crosswalk.resolve(regions=["01", "19"]).method == "tmt_maakunta_multiple_nuts3"
    # An ambiguous region key is reported, never guessed.
    assert crosswalk.resolve(regions=["02"]).method == "tmt_maakunta_ambiguous_code"
    # Unknown codes are unmapped; no codes at all is not_present.
    unknown = crosswalk.resolve(municipalities=["999"], regions=["77"])
    assert (unknown.nuts_code, unknown.status, unknown.method) == (
        None,
        "unmapped",
        "tmt_unknown_region_code",
    )
    absent = crosswalk.resolve(municipalities=[], regions=[])
    assert (absent.status, absent.method) == ("not_present", "not_available")
    # Zero-padding is folded on both sides.
    assert crosswalk.resolve(municipalities=["91"]).nuts_code == "FI1B1"
    assert crosswalk.resolve(regions=["1"]).nuts_code == "FI1B1"


def test_a_missing_or_empty_crosswalk_is_a_loud_failure(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="reference_finland"):
        FinlandCrosswalk(tmp_path)
    (tmp_path / TMT_REFERENCE_FILE).write_text(HEADER, encoding="utf-8")
    with pytest.raises(ValueError, match="is empty"):
        FinlandCrosswalk(tmp_path)


def test_the_reference_hash_is_content_addressed(reference_dir: Path) -> None:
    first = crosswalk_reference_hashes(reference_dir)
    assert first.startswith(f"{TMT_REFERENCE_FILE}:")
    assert len(first.split(":")[1]) == 64
    (reference_dir / TMT_REFERENCE_FILE).write_text(
        HEADER + ROWS + "kunta,179,FI198,Keski-Suomi,https://example.invalid/kunta,2026-08-23\n",
        encoding="utf-8",
    )
    assert crosswalk_reference_hashes(reference_dir) != first


def test_code_normalizers_are_shared_and_total() -> None:
    assert normalize_kunta_code("91") == "091"
    assert normalize_kunta_code(" 091 ") == "091"
    assert normalize_kunta_code("1234") == "1234"  # never truncated
    assert normalize_kunta_code(None) == ""
    assert normalize_kunta_code("") == ""
    assert normalize_maakunta_code("1") == "01"
    assert normalize_maakunta_code("21") == "21"


# ---------------------------------------------------------------------------
# Field mapping, timestamps and PII isolation
# ---------------------------------------------------------------------------


@respx.mock
def test_the_allowlist_fields_are_mapped_from_the_documented_payload(
    reference_dir: Path,
) -> None:
    mock_robots(respx.mock)
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson(
                posting(
                    "a-1",
                    municipalities=["853"],
                    languages=["sv", "fi"],
                    open_positions=4,
                    archived="2026-08-23T06:00:00.000000",
                )
            ),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    row = run(collect(build(reference_dir)))[0]

    assert row.source == "tmt"
    assert row.country == "FI"
    assert len(row.source_id) == 64
    assert int(row.source_id, 16) >= 0  # hex digest
    assert row.scope_id == "fi-all-active"
    assert row.sweep_id == "20260823T000000Z"
    assert row.first_published == datetime(2026, 8, 20, 8, 15, tzinfo=UTC)
    assert row.last_modified == datetime(2026, 8, 21, 9, 34, 28, 673623, tzinfo=UTC)
    assert row.removed_at == datetime(2026, 8, 23, 6, 0, tzinfo=UTC)
    assert row.nuts_code == "FI1C1"
    assert row.nuts_version == "NUTS-2024"
    assert row.number_of_vacancies == 4
    assert row.lang == row.source_language == "sv"
    assert row.jobtech_taxonomy_version == ""
    assert row.esco_version == "1.2.1"


@respx.mock
def test_first_published_falls_back_to_metadata_created(reference_dir: Path) -> None:
    """The schema says ``published`` may be null for immediate publication."""
    mock_robots(respx.mock)
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson(
                posting("a-1", published=None, created="2026-08-18T06:30:00.000000"),
                posting("a-2", published=None, created=""),
            ),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    rows = run(collect(build(reference_dir)))
    assert rows[0].first_published == datetime(2026, 8, 18, 6, 30, tzinfo=UTC)
    assert rows[1].first_published is None
    assert all(row.removed_at is None for row in rows)


@respx.mock
def test_missing_optional_blocks_default_safely(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson({"languages": [], "metadata": {"externalId": "a-1"}}),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    row = run(collect(build(reference_dir)))[0]
    assert row.number_of_vacancies == 1
    assert row.lang == "fi"  # documented default language of the portal
    assert row.first_published is None
    assert row.last_modified is None
    assert row.region_mapping_status == "not_present"
    assert row.occupation_mapping_status == "not_present"
    assert row.skill_mappings == []


def test_timestamps_are_read_as_utc_when_the_source_omits_an_offset() -> None:
    # maxLength 26 leaves no room for a designator, so naive is the expected form.
    assert parse_tmt_datetime("2026-08-21T09:34:28.673623") == datetime(
        2026, 8, 21, 9, 34, 28, 673623, tzinfo=UTC
    )
    # An explicit offset is honored when present.
    assert parse_tmt_datetime("2026-08-21T11:34:28+02:00") == datetime(
        2026, 8, 21, 9, 34, 28, tzinfo=UTC
    )
    assert parse_tmt_datetime("2026-08-21T09:34:28Z") == datetime(
        2026, 8, 21, 9, 34, 28, tzinfo=UTC
    )
    assert parse_tmt_datetime("not a timestamp") is None
    assert parse_tmt_datetime("") is None
    assert parse_tmt_datetime(None) is None


@respx.mock
def test_no_pii_reaches_the_record_or_the_intermediate_raw_record(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text=ndjson(posting("11111111-2222-3333-4444-555555555555")),
            headers={"content-type": "application/x-ndjson"},
        )
    )
    collector = build(reference_dir)

    async def drive() -> tuple[dict[str, Any], dict[str, Any]]:
        async with collector:
            raws = [raw async for raw in collector.fetch()]
            return raws[0].payload, collector.normalize(collector.parse(raws[0])).model_dump(
                mode="json"
            )

    raw_payload, dumped = run(drive())

    forbidden = (
        "Yksityinen",
        "Yhteyshenkilo",
        "privat@example.invalid",
        "0401234567",
        "040 123 4567",
        "Private Employer Oy",
        "Private Principal Oy",
        "Private Job Title",
        "Private Workplace",
        "example.invalid",
        "00100",
        "1234567-8",
        "8765432-1",
        "REQ-2026-0001",
        "Private Household Person",
        "62010",
        "11111111-2222-3333-4444-555555555555",
    )
    for blob, label in ((raw_payload, "RawRecord"), (dumped, "NormalizedRecord")):
        serialized = json.dumps(blob, ensure_ascii=False)
        for needle in forbidden:
            if label == "RawRecord" and needle == "11111111-2222-3333-4444-555555555555":
                continue  # RawRecord.native_id carries the id by contract
            assert needle not in serialized, f"{needle} leaked into {label}"

    # The RawRecord payload holds only the five declared blocks.
    assert set(raw_payload) == {"languages", "metadata", "position", "location", "application"}
    assert set(raw_payload["position"]) == {"mainOccupation", "occupations", "skills"}
    assert set(raw_payload["location"]) == {"countries", "regions", "municipalities"}
    assert set(raw_payload["application"]) == {"published", "expires", "openPositions"}
    assert "contacts" not in raw_payload
    assert "owner" not in raw_payload


def test_the_output_carries_exactly_the_allowlist_fields(reference_dir: Path) -> None:
    collector = build(reference_dir)
    raw = RawRecord(native_id="a-1", payload=posting("a-1"))
    row = collector.normalize(collector.parse(raw))
    assert set(row.model_dump()) == {
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
