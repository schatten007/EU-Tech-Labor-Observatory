"""Unit tests for NAVFeedCollector (Increment 6) against mocked feed fixtures.

Covers the two auth routes (private ``NAV_FEED_TOKEN`` and the public token
endpoint) plus the documented irregular rotation (401 -> refresh once -> replay),
``next_url`` pagination to a null ``next_id``, ``304`` revalidation treated as
"unchanged", the event fold per ad uuid in both orderings, source-reported
``removed_at``, content-masked INACTIVE details, ``positioncount`` string
coercion, ESCO extraction (single, multiple, tie, malformed, absent), region
resolution across the three signals, PII isolation, ``429`` backoff honoring
``Retry-After`` and malformed pages.

Fixtures are hand-written synthetic payloads modelled on the live contract; no
real employer, person or vacancy text is stored in the repository.
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

from scrapers.base import NormalizedRecord
from scrapers.nav_norway import (
    NAV_BASE,
    NAV_FEED_URL,
    NAV_PUBLIC_TOKEN_URL,
    NAV_REFERENCE_FILE,
    NAV_ROBOTS_URL,
    FeedCursor,
    NavCategory,
    NAVCrosswalk,
    NAVFeedCollector,
    crosswalk_reference_hashes,
    http_date,
    load_cached_token,
    load_cursor,
    normalize_region_name,
    parse_nav_datetime,
    parse_position_count,
    parse_public_token,
    resolve_occupation,
    save_cached_token,
    save_cursor,
    score_confidence,
)
from scrapers.retry import RetryPolicy
from scrapers.robots import RobotsDisallowedError

KEY = b"test-only-key-with-at-least-32-bytes"

TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.c2lnbmF0dXJl"
TOKEN_BODY = f"Current public token for Nav Job Vacancy Feed:\n{TOKEN}"

HEADER = "source_type,source_code,nuts_code,nuts_label,source_url,source_version\n"
ROWS = (
    "fylke,vestland,NO0A2,Vestland,https://example.invalid/104,2026-08-23\n"
    "fylke,oslo,NO081,Oslo,https://example.invalid/104,2026-08-23\n"
    "fylke,troms,NO072,Troms/Romsa/Tromssa,https://example.invalid/104,2026-08-23\n"
    "kommune,bergen,NO0A2,Vestland,https://example.invalid/131,2026-08-23\n"
    "kommune,oslo,NO081,Oslo,https://example.invalid/131,2026-08-23\n"
    "kommune,tromso,NO072,Troms/Romsa/Tromssa,https://example.invalid/131,2026-08-23\n"
    "kommune,ostre toten,NO020,Innlandet,https://example.invalid/131,2026-08-23\n"
    "kommune-ambiguous,heroy,,,https://example.invalid/131,2026-08-23\n"
)

ESCO_URI = "http://data.europa.eu/esco/occupation/0b15375e-dfdd-4047-9efb-096e0aaee7d2"
ESCO_URI_2 = "http://data.europa.eu/esco/occupation/4fa660b3-ab97-4a99-ad73-ce3c2612f2c3"


def feed_item(
    uuid: str,
    *,
    status: str = "ACTIVE",
    municipal: str = "BERGEN",
    sist_endret: str = "2026-08-21T09:34:28.673623+02:00",
    date_modified: str | None = None,
) -> dict[str, Any]:
    """One synthetic feed event carrying the PII the allowlist must never let through."""
    return {
        "id": f"entry-{uuid}",
        "url": f"/api/v1/feedentry/{uuid}",
        "title": "Private Job Title",
        "content_text": "Private annonsetekst med kontakt 999 88 777.",
        "date_modified": date_modified or sist_endret,
        "_feed_entry": {
            "uuid": uuid,
            "status": status,
            "title": "Private Job Title",
            "businessName": "Private Employer AS",
            "municipal": municipal,
            "sistEndret": sist_endret,
        },
    }


def feed_page(
    items: list[dict[str, Any]],
    *,
    page_id: str = "page-1",
    next_id: str | None = "page-2",
) -> dict[str, Any]:
    return {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "Stillingsfeeden fra arbeidsplassen.no",
        "home_page_url": "https://arbeidsplassen.nav.no",
        "feed_url": f"/api/v1/feed/{page_id}",
        "description": "Feed med stillinger",
        "next_url": f"/api/v1/feed/{next_id}" if next_id else None,
        "id": page_id,
        "next_id": next_id,
        "items": items,
    }


def ad_detail(
    uuid: str,
    *,
    status: str = "ACTIVE",
    positioncount: Any = "2",
    county: str | None = "VESTLAND",
    municipal: str | None = "BERGEN",
    country: str = "NORGE",
    categories: list[dict[str, Any]] | None = None,
    masked: bool = False,
    published: str = "2026-08-21T00:00:00+02:00",
    updated: str = "2026-08-21T09:46:01.790496+02:00",
) -> dict[str, Any]:
    """One synthetic ad detail; ``masked`` reproduces an actively-stopped ad."""
    payload: dict[str, Any] = {
        "uuid": uuid,
        "status": status,
        "sistEndret": "2026-08-21T09:46:01.790496+02:00",
    }
    if masked:
        return payload
    payload["ad_content"] = {
        "uuid": uuid,
        "published": published,
        "updated": updated,
        "expires": "2026-09-06T00:00:00+02:00",
        "title": "Private Job Title",
        "jobtitle": "Private Job Title",
        "description": "Privat omtale med e-post privat@example.invalid og telefon 999 88 777.",
        "employer": {
            "name": "Private Employer AS",
            "orgnr": "999888777",
            "description": "Privat verksemd",
            "homepage": "https://employer.example.invalid",
        },
        "contactList": [
            {
                "name": "Privat Kontaktperson",
                "email": "privat@example.invalid",
                "phone": "99988777",
                "role": "Leiar",
                "title": "Dagleg leiar",
            }
        ],
        "applicationUrl": "https://apply.example.invalid/1",
        "applicationDue": "2026-09-01",
        "sourceurl": "https://source.example.invalid/1",
        "source": "IMPORTAPI",
        "link": "https://arbeidsplassen.nav.no/stillinger/stilling/private",
        "workLocations": [
            {
                "country": country,
                "address": "Privatvegen 35",
                "city": "BERGEN",
                "postalCode": "5003",
                "county": county,
                "municipal": municipal,
            }
        ],
        "occupationCategories": [{"level1": "Salg og service", "level2": "Butikk"}],
        "categoryList": (
            categories
            if categories is not None
            else [
                {
                    "categoryType": "ESCO",
                    "code": ESCO_URI,
                    "name": "butikkmedarbeider",
                    "description": "",
                    "score": 1.0,
                },
                {"categoryType": "JANZZ", "code": "113087", "name": "Butikk", "score": 1.0},
                {"categoryType": "STYRK08", "code": "5223", "name": "Butikk", "score": 1.0},
            ]
        ),
        "engagementtype": "Fast",
        "extent": "Deltid",
        "starttime": "Snarast",
        "positioncount": positioncount,
        "sector": "Privat",
    }
    return payload


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


@pytest.fixture
def reference_dir(tmp_path: Path) -> Path:
    (tmp_path / NAV_REFERENCE_FILE).write_text(HEADER + ROWS, encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def _no_ambient_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep a developer's real ``NAV_FEED_TOKEN`` / ``.env`` out of the tests."""
    monkeypatch.delenv("NAV_FEED_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)


def make_collector(
    reference_dir: Path,
    *,
    since_days: int | None = 2,
    max_pages: int | None = None,
    max_details: int | None = None,
    token: str | None = None,
    cursor_path: Path | None = None,
    token_cache_path: Path | None = None,
    use_cursor: bool = True,
    policy: RetryPolicy | None = None,
) -> NAVFeedCollector:
    return NAVFeedCollector(
        scope_id="no-all-events",
        sweep_id="20260823T000000Z",
        observed_at=datetime(2026, 8, 23, tzinfo=UTC),
        hmac_key=KEY,
        reference_dir=reference_dir,
        since_days=since_days,
        max_pages=max_pages,
        max_details=max_details,
        token=token,
        cursor_path=cursor_path,
        token_cache_path=token_cache_path,
        use_cursor=use_cursor,
        pacing_interval=0.0,
        policy=policy,
    )


def collect(collector: NAVFeedCollector) -> list[NormalizedRecord]:
    async def go() -> list[NormalizedRecord]:
        async with collector:
            return [record async for record in collector.collect()]

    return run(go())


def mock_robots(router: respx.Router, *, status: int = 404) -> None:
    router.get(NAV_ROBOTS_URL).mock(
        return_value=httpx.Response(
            status,
            json={"title": "Endpoint GET /robots.txt not found", "status": 404},
        )
        if status == 404
        else httpx.Response(status, text="User-agent: *\nDisallow:\n")
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_public_token_is_the_last_line_of_the_plain_text_body() -> None:
    assert parse_public_token(TOKEN_BODY) == TOKEN


@pytest.mark.parametrize("body", ["", "no token here", "Current token:\nnot.a", "a.b.\n"])
def test_public_token_body_without_a_three_segment_jwt_raises(body: str) -> None:
    with pytest.raises(RuntimeError, match="3-segment JWT"):
        parse_public_token(body)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2", 2),
        ("1", 1),
        ("0", 0),
        ("", 1),
        ("  3 ", 3),
        (None, 1),
        ("abc", 1),
        ("2.0", 2),
        ("-4", 0),
        (5, 5),
        (2.0, 2),
    ],
)
def test_position_count_coercion(value: Any, expected: int) -> None:
    """``positioncount`` is a string at source; garbage must not crash a sweep."""
    assert parse_position_count(value) == expected


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("TRØNDELAG", "Trøndelag - Trööndelage"),
        ("TRØNDELAG", "Trøndelag/Trööndelage"),
        ("NORDLAND", "Nordland - Nordlánnda"),
        ("TROMS", "Troms/Romsa/Tromssa"),
        ("OSLO", "Oslo - Oslove"),
        ("MØRE OG ROMSDAL", "Møre og Romsdal"),
        ("HERØY", "Herøy (Nordland)"),
        ("VÅLER", "Våler (Østfold)"),
        ("ØSTRE TOTEN", "Østre Toten"),
    ],
)
def test_region_name_folding_matches_ssb_gisco_and_the_feed(left: str, right: str) -> None:
    assert normalize_region_name(left) == normalize_region_name(right)


def test_region_name_folding_keeps_inner_hyphenated_names_distinct() -> None:
    """``Nord-Odal`` is one name, not a Sami dual name; it must not be truncated."""
    assert normalize_region_name("NORD-ODAL") == "nord odal"
    assert normalize_region_name("AURSKOG-HØLAND") == "aurskog holand"
    assert normalize_region_name("STOR-ELVDAL") != normalize_region_name("STOR")
    assert normalize_region_name(None) == ""


def test_http_date_is_locale_independent_rfc_1123() -> None:
    assert http_date(datetime(2026, 8, 20, 21, 41, 51, tzinfo=UTC)) == (
        "Thu, 20 Aug 2026 21:41:51 GMT"
    )


def test_nav_datetime_parsing_is_total() -> None:
    parsed = parse_nav_datetime("2026-08-21T09:46:01.790496+02:00")
    assert parsed is not None and parsed.tzinfo is not None
    assert parse_nav_datetime("2026-08-21T00:00:00Z") is not None
    naive = parse_nav_datetime("2026-08-21T00:00:00")
    assert naive is not None and naive.tzinfo is UTC
    assert parse_nav_datetime("not a date") is None
    assert parse_nav_datetime(None) is None


@pytest.mark.parametrize(
    ("score", "expected"),
    [(1.0, "high"), (0.9, "high"), (0.75, "medium"), (0.6, "medium"), (0.1, "low"), (0.0, "low")],
)
def test_score_confidence_buckets(score: float, expected: str) -> None:
    assert score_confidence(score) == expected


def test_score_confidence_is_none_when_the_source_gives_no_score() -> None:
    assert score_confidence(None) is None


# ---------------------------------------------------------------------------
# ESCO extraction
# ---------------------------------------------------------------------------


def test_esco_uri_is_taken_straight_from_categorylist() -> None:
    resolution = resolve_occupation(
        [
            NavCategory(categoryType="JANZZ", code="21187", score=1.0),
            NavCategory(categoryType="ESCO", code=ESCO_URI, score=1.0),
            NavCategory(categoryType="STYRK08", code="5329", score=1.0),
        ]
    )
    assert resolution.uri == ESCO_URI
    assert resolution.status == "mapped"
    assert resolution.confidence == "high"
    assert resolution.method == "nav_categorylist_esco"


def test_highest_scoring_esco_entry_wins() -> None:
    resolution = resolve_occupation(
        [
            NavCategory(categoryType="ESCO", code=ESCO_URI, score=0.4),
            NavCategory(categoryType="esco", code=ESCO_URI_2, score=0.95),
        ]
    )
    assert resolution.uri == ESCO_URI_2
    assert resolution.status == "mapped"
    assert resolution.confidence == "high"


def test_tied_esco_scores_are_ambiguous_but_still_report_a_uri() -> None:
    resolution = resolve_occupation(
        [
            NavCategory(categoryType="ESCO", code=ESCO_URI, score=1.0),
            NavCategory(categoryType="ESCO", code=ESCO_URI_2, score=1.0),
        ]
    )
    assert resolution.status == "ambiguous"
    assert resolution.uri in {ESCO_URI, ESCO_URI_2}


def test_no_esco_entry_is_not_present_while_an_unusable_one_is_unmapped() -> None:
    absent = resolve_occupation([NavCategory(categoryType="STYRK08", code="5223", score=1.0)])
    assert (absent.status, absent.uri) == ("not_present", None)
    unrecognized = resolve_occupation([NavCategory(categoryType="ESCO", code="21187", score=1.0)])
    assert unrecognized.status == "unmapped"
    assert unrecognized.uri is None
    assert unrecognized.method == "nav_categorylist_esco_unrecognized"


def test_an_isco_group_uri_is_refused_with_its_own_method_name() -> None:
    """Measured live: NAV labels ISCO-08 group URIs ``categoryType: "ESCO"``.

    An ISCO group is a coarser concept scheme than an ESCO occupation, so writing
    it into ``esco_occupation_uri`` would corrupt downstream joins.
    """
    resolution = resolve_occupation(
        [
            NavCategory(
                categoryType="ESCO", code="http://data.europa.eu/esco/isco/c9112", score=1.0
            ),
            NavCategory(categoryType="STYRK08", code="9112", score=1.0),
        ]
    )
    assert resolution.uri is None
    assert resolution.status == "unmapped"
    assert resolution.method == "nav_categorylist_esco_isco_group"


def test_an_occupation_uri_still_wins_when_an_isco_group_is_also_present() -> None:
    resolution = resolve_occupation(
        [
            NavCategory(
                categoryType="ESCO", code="http://data.europa.eu/esco/isco/c9112", score=1.0
            ),
            NavCategory(categoryType="ESCO", code=ESCO_URI, score=0.8),
        ]
    )
    assert resolution.uri == ESCO_URI
    assert resolution.status == "mapped"
    assert resolution.confidence == "medium"


def test_an_empty_esco_code_is_unmapped() -> None:
    resolution = resolve_occupation([NavCategory(categoryType="ESCO", code="", score=1.0)])
    assert resolution.status == "unmapped"
    assert resolution.method == "nav_categorylist_esco_unrecognized"


def test_no_categories_at_all_is_not_present() -> None:
    assert resolve_occupation([]).status == "not_present"


# ---------------------------------------------------------------------------
# Region crosswalk
# ---------------------------------------------------------------------------


def test_crosswalk_prefers_the_county_then_the_municipality(reference_dir: Path) -> None:
    crosswalk = NAVCrosswalk(reference_dir)
    assert crosswalk.lookup_fylke("VESTLAND") == ("NO0A2", "Vestland")
    assert crosswalk.lookup_kommune("BERGEN") == ("NO0A2", "Vestland")
    assert crosswalk.lookup_kommune("UKJENT") is None
    assert crosswalk.kommune_is_ambiguous("HERØY") is True
    assert crosswalk.kommune_is_ambiguous("BERGEN") is False
    assert crosswalk.fylker() == ["oslo", "troms", "vestland"]
    assert "bergen" in crosswalk.kommuner()


def test_crosswalk_missing_file_and_empty_file_fail_loudly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="reference_nav"):
        NAVCrosswalk(tmp_path)
    (tmp_path / NAV_REFERENCE_FILE).write_text(HEADER, encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        NAVCrosswalk(tmp_path)


def test_reference_hashes_are_content_addressed(reference_dir: Path) -> None:
    first = crosswalk_reference_hashes(reference_dir)
    assert first.startswith(f"{NAV_REFERENCE_FILE}:")
    (reference_dir / NAV_REFERENCE_FILE).write_text(HEADER + ROWS + "\n", encoding="utf-8")
    assert crosswalk_reference_hashes(reference_dir) != first


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@respx.mock
def test_private_token_from_the_environment_skips_the_token_endpoint(
    reference_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NAV_FEED_TOKEN", "private.jwt.token")
    mock_robots(respx.mock)
    token_route = respx.get(NAV_PUBLIC_TOKEN_URL).mock(
        return_value=httpx.Response(200, text=TOKEN_BODY)
    )
    feed = respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id=None))
    )
    collector = make_collector(reference_dir, max_details=0)
    rows = collect(collector)
    assert len(rows) == 1
    assert not token_route.called
    assert collector.token_requests == 0
    assert feed.calls[0].request.headers["Authorization"] == "Bearer private.jwt.token"


@respx.mock
def test_private_token_from_dotenv_is_used(reference_dir: Path, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("NAV_FEED_TOKEN=dotenv.jwt.token\n", encoding="utf-8")
    mock_robots(respx.mock)
    feed = respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id=None))
    )
    collect(make_collector(reference_dir, max_details=0))
    assert feed.calls[0].request.headers["Authorization"] == "Bearer dotenv.jwt.token"


@respx.mock
def test_public_token_is_fetched_once_and_reused(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    token_route = respx.get(NAV_PUBLIC_TOKEN_URL).mock(
        return_value=httpx.Response(200, text=TOKEN_BODY)
    )
    respx.get(f"{NAV_BASE}/api/v1/feed/page-2").mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("b")], next_id=None))
    )
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id="page-2"))
    )
    collector = make_collector(reference_dir, max_details=0)
    rows = collect(collector)
    assert len(rows) == 2
    assert token_route.call_count == 1
    assert collector.token_requests == 1


@respx.mock
def test_401_refreshes_the_token_once_and_replays_the_request(reference_dir: Path) -> None:
    """The public token rotates at irregular intervals; that is not downtime."""
    mock_robots(respx.mock)
    token_route = respx.get(NAV_PUBLIC_TOKEN_URL).mock(
        side_effect=[
            httpx.Response(200, text="Current public token:\nstale.jwt.token"),
            httpx.Response(200, text=TOKEN_BODY),
        ]
    )
    feed_route = respx.get(NAV_FEED_URL).mock(
        side_effect=[
            httpx.Response(401, json={"title": "Unauthorized", "status": 401}),
            httpx.Response(200, json=feed_page([feed_item("a")], next_id=None)),
        ]
    )
    collector = make_collector(reference_dir, max_details=0)
    rows = collect(collector)
    assert len(rows) == 1
    assert token_route.call_count == 2
    assert collector.token_requests == 2
    assert collector.token_refreshes == 1
    assert feed_route.calls[0].request.headers["Authorization"] == "Bearer stale.jwt.token"
    assert feed_route.calls[1].request.headers["Authorization"] == f"Bearer {TOKEN}"


@respx.mock
def test_a_second_401_is_a_real_error(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(401, json={"title": "Unauthorized", "status": 401})
    )
    with pytest.raises(httpx.HTTPStatusError):
        collect(make_collector(reference_dir, max_details=0))


@respx.mock
def test_the_public_token_is_cached_on_disk_between_sweeps(
    reference_dir: Path, tmp_path: Path
) -> None:
    """NAV's token endpoint is slow (26-28 s measured) and rotates rarely."""
    cache = tmp_path / "token.json"
    mock_robots(respx.mock)
    token_route = respx.get(NAV_PUBLIC_TOKEN_URL).mock(
        return_value=httpx.Response(200, text=TOKEN_BODY)
    )
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id=None))
    )
    first = make_collector(reference_dir, max_details=0, token_cache_path=cache)
    collect(first)
    assert token_route.call_count == 1
    assert load_cached_token(cache) == TOKEN

    second = make_collector(reference_dir, max_details=0, token_cache_path=cache)
    collect(second)
    assert token_route.call_count == 1  # reused from disk, not re-fetched
    assert second.token_requests == 0


@respx.mock
def test_a_rotation_bypasses_the_cache_and_rewrites_it(reference_dir: Path, tmp_path: Path) -> None:
    cache = tmp_path / "token.json"
    save_cached_token("stale.jwt.token", cache)
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        side_effect=[
            httpx.Response(401, json={"title": "Unauthorized", "status": 401}),
            httpx.Response(200, json=feed_page([feed_item("a")], next_id=None)),
        ]
    )
    collector = make_collector(reference_dir, max_details=0, token_cache_path=cache)
    assert len(collect(collector)) == 1
    assert collector.token_refreshes == 1
    assert load_cached_token(cache) == TOKEN


def test_a_malformed_token_cache_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "token.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_cached_token(path) is None
    path.write_text(json.dumps({"token": "not-a-jwt"}), encoding="utf-8")
    assert load_cached_token(path) is None
    path.write_text(json.dumps({"token": "a.b."}), encoding="utf-8")
    assert load_cached_token(path) is None
    assert load_cached_token(tmp_path / "absent.json") is None


# ---------------------------------------------------------------------------
# robots gate
# ---------------------------------------------------------------------------


@respx.mock
def test_absent_robots_allows_the_feed_and_is_fetched_first(reference_dir: Path) -> None:
    robots = respx.get(NAV_ROBOTS_URL).mock(
        return_value=httpx.Response(404, json={"title": "not found", "status": 404})
    )
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id=None))
    )
    collect(make_collector(reference_dir, max_details=0))
    assert robots.called
    assert respx.calls[0].request.url.path == "/robots.txt"


@respx.mock
def test_a_served_robots_file_is_enforced_per_url(reference_dir: Path) -> None:
    respx.get(NAV_ROBOTS_URL).mock(
        return_value=httpx.Response(
            200,
            text="User-agent: *\nDisallow: /api/v1/feed\n",
            headers={"Content-Type": "text/plain"},
        )
    )
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    with pytest.raises(RobotsDisallowedError, match="disallows"):
        collect(make_collector(reference_dir, max_details=0))


def test_no_request_is_allowed_before_robots_is_loaded(reference_dir: Path) -> None:
    collector = make_collector(reference_dir)
    with pytest.raises(RobotsDisallowedError, match="not loaded"):
        collector.assert_allowed(NAV_FEED_URL)


# ---------------------------------------------------------------------------
# Pagination, revalidation and the cursor
# ---------------------------------------------------------------------------


@respx.mock
def test_pagination_follows_next_url_until_next_id_is_null(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(
            200,
            json=feed_page([feed_item("a")], page_id="page-1", next_id="page-2"),
            headers={"ETag": "page-2"},
        )
    )
    respx.get(f"{NAV_BASE}/api/v1/feed/page-2").mock(
        return_value=httpx.Response(
            200,
            json=feed_page([feed_item("b")], page_id="page-2", next_id="page-3"),
            headers={"ETag": "page-3"},
        )
    )
    respx.get(f"{NAV_BASE}/api/v1/feed/page-3").mock(
        return_value=httpx.Response(
            200,
            json=feed_page([feed_item("c")], page_id="page-3", next_id=None),
            headers={"ETag": "page-4"},
        )
    )
    collector = make_collector(reference_dir, max_details=0)
    rows = collect(collector)
    assert len(rows) == 3
    assert collector.completed_pages == 3
    assert collector.total_pages == collector.completed_pages
    assert collector.total_elements == 3
    assert collector.events_seen == 3


@respx.mock
def test_the_seek_page_carries_if_modified_since_and_nothing_else(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    feed = respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id=None))
    )
    collector = make_collector(reference_dir, since_days=2, max_details=0)
    collect(collector)
    request = feed.calls[0].request
    assert request.headers["If-Modified-Since"] == "Fri, 21 Aug 2026 00:00:00 GMT"
    assert "If-None-Match" not in request.headers
    assert collector.since_header == "Fri, 21 Aug 2026 00:00:00 GMT"


@respx.mock
def test_page_budget_stops_the_walk_and_the_manifest_still_reconciles(
    reference_dir: Path,
) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id="page-2"))
    )
    page2 = respx.get(f"{NAV_BASE}/api/v1/feed/page-2").mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("b")], next_id=None))
    )
    collector = make_collector(reference_dir, max_pages=1, max_details=0)
    rows = collect(collector)
    assert len(rows) == 1
    assert not page2.called
    assert collector.total_pages == collector.completed_pages == 1


@respx.mock
def test_304_on_revalidation_means_unchanged_not_an_error(
    reference_dir: Path, tmp_path: Path
) -> None:
    """A poll that finds nothing new writes zero rows and a reconciled manifest."""
    cursor_path = tmp_path / "cursor.json"
    save_cursor(
        FeedCursor(page_url="/api/v1/feed/page-9", etag="page-10", next_url=None), cursor_path
    )
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    page = respx.get(f"{NAV_BASE}/api/v1/feed/page-9").mock(
        return_value=httpx.Response(304, headers={"ETag": "page-10"})
    )
    collector = make_collector(
        reference_dir, since_days=None, cursor_path=cursor_path, max_details=0
    )
    rows = collect(collector)
    assert rows == []
    assert collector.pages_unchanged == 1
    assert collector.resumed_from_cursor is True
    assert collector.total_pages == collector.completed_pages == 1
    assert collector.total_elements == 0
    assert page.calls[0].request.headers["If-None-Match"] == "page-10"
    # If-Modified-Since must NOT be sent with If-None-Match: it re-seeks (live).
    assert "If-Modified-Since" not in page.calls[0].request.headers
    # The cursor survives an unchanged poll.
    assert load_cursor(cursor_path) is not None


@respx.mock
def test_the_cursor_resumes_from_next_url_when_the_previous_sweep_stopped_mid_feed(
    reference_dir: Path, tmp_path: Path
) -> None:
    cursor_path = tmp_path / "cursor.json"
    save_cursor(
        FeedCursor(page_url="/api/v1/feed/page-1", etag="page-2", next_url="/api/v1/feed/page-2"),
        cursor_path,
    )
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    seek = respx.get(NAV_FEED_URL).mock(return_value=httpx.Response(200, json=feed_page([])))
    page2 = respx.get(f"{NAV_BASE}/api/v1/feed/page-2").mock(
        return_value=httpx.Response(
            200,
            json=feed_page([feed_item("b")], page_id="page-2", next_id=None),
            headers={"ETag": "page-3", "Last-Modified": "Fri, 21 Aug 2026 13:58:03 +0200"},
        )
    )
    collector = make_collector(
        reference_dir, since_days=None, cursor_path=cursor_path, max_details=0
    )
    rows = collect(collector)
    assert len(rows) == 1
    assert not seek.called
    assert "If-None-Match" not in page2.calls[0].request.headers
    saved = load_cursor(cursor_path)
    assert saved is not None
    assert saved.page_url == "/api/v1/feed/page-2"
    assert saved.etag == "page-3"
    assert saved.next_url is None


@respx.mock
def test_an_explicit_since_overrides_the_cursor(reference_dir: Path, tmp_path: Path) -> None:
    cursor_path = tmp_path / "cursor.json"
    save_cursor(FeedCursor(page_url="/api/v1/feed/page-1", etag="page-2"), cursor_path)
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    seek = respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id=None))
    )
    collector = make_collector(reference_dir, since_days=3, cursor_path=cursor_path, max_details=0)
    collect(collector)
    assert seek.called
    assert collector.resumed_from_cursor is False


def test_a_corrupt_cursor_is_ignored_rather_than_crashing_the_poll(tmp_path: Path) -> None:
    path = tmp_path / "cursor.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_cursor(path) is None
    assert load_cursor(tmp_path / "absent.json") is None


# ---------------------------------------------------------------------------
# Event folding
# ---------------------------------------------------------------------------


@respx.mock
def test_repeated_events_for_one_uuid_fold_to_the_latest_state(reference_dir: Path) -> None:
    """ACTIVE -> INACTIVE: the row is closed with the last event's timestamp."""
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(
            200,
            json=feed_page(
                [
                    feed_item("a", status="ACTIVE", sist_endret="2026-08-21T08:00:00+02:00"),
                    feed_item("a", status="ACTIVE", sist_endret="2026-08-21T09:00:00+02:00"),
                    feed_item("a", status="INACTIVE", sist_endret="2026-08-21T10:00:00+02:00"),
                ],
                next_id=None,
            ),
        )
    )
    collector = make_collector(reference_dir, max_details=0)
    rows = collect(collector)
    assert len(rows) == 1
    assert collector.events_seen == 3
    assert rows[0].removed_at is not None
    assert rows[0].removed_at.isoformat() == "2026-08-21T10:00:00+02:00"


@respx.mock
def test_a_reactivated_ad_is_not_stamped_removed(reference_dir: Path) -> None:
    """INACTIVE -> ACTIVE: the later ACTIVE event wins, so removed_at is None."""
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(
            200,
            json=feed_page(
                [
                    feed_item("a", status="INACTIVE", sist_endret="2026-08-21T08:00:00+02:00"),
                    feed_item("a", status="ACTIVE", sist_endret="2026-08-21T11:00:00+02:00"),
                ],
                next_id=None,
            ),
        )
    )
    respx.get(f"{NAV_BASE}/api/v1/feedentry/a").mock(
        return_value=httpx.Response(200, json=ad_detail("a"))
    )
    rows = collect(make_collector(reference_dir, max_details=5))
    assert len(rows) == 1
    assert rows[0].removed_at is None


@respx.mock
def test_folding_is_keyed_on_the_hmac_digest_not_the_native_uuid(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(
            200,
            json=feed_page(
                [feed_item("a"), feed_item("b"), feed_item("a"), feed_item("c")], next_id=None
            ),
        )
    )
    rows = collect(make_collector(reference_dir, max_details=0))
    ids = {row.source_id for row in rows}
    assert len(rows) == 3
    assert len(ids) == 3
    assert all(len(source_id) == 64 for source_id in ids)
    assert all(int(source_id, 16) >= 0 for source_id in ids)


# ---------------------------------------------------------------------------
# Details
# ---------------------------------------------------------------------------


@respx.mock
def test_active_detail_populates_dates_vacancies_region_and_esco(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id=None))
    )
    respx.get(f"{NAV_BASE}/api/v1/feedentry/a").mock(
        return_value=httpx.Response(200, json=ad_detail("a", positioncount="2"))
    )
    collector = make_collector(reference_dir, max_details=5)
    rows = collect(collector)
    row = rows[0]
    assert row.first_published is not None and row.first_published.year == 2026
    assert row.last_modified is not None
    assert row.number_of_vacancies == 2
    assert (row.nuts_code, row.region_mapping_status) == ("NO0A2", "mapped")
    assert row.region_mapping_method == "nav_worklocation_county_nuts3"
    assert row.esco_occupation_uri == ESCO_URI
    assert row.occupation_mapping_status == "mapped"
    assert row.occupation_mapping_confidence == "high"
    assert row.esco_occupation_label is None
    assert row.skill_mappings == []
    assert collector.details_with_content == 1
    assert collector.rows_with_esco == 1


@respx.mock
def test_inactive_ads_never_cost_a_detail_request(reference_dir: Path) -> None:
    """Measured live: only 2 of 20 INACTIVE details still carry ad_content."""
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(
            200,
            json=feed_page(
                [feed_item("a", status="INACTIVE", municipal="OSLO")],
                next_id=None,
            ),
        )
    )
    detail = respx.get(f"{NAV_BASE}/api/v1/feedentry/a").mock(
        return_value=httpx.Response(200, json=ad_detail("a", masked=True))
    )
    collector = make_collector(reference_dir, max_details=100)
    rows = collect(collector)
    assert not detail.called
    assert collector.detail_requests == 0
    row = rows[0]
    assert row.removed_at is not None
    assert row.first_published is None
    assert row.last_modified is not None  # sistEndret is the source's own stamp
    assert (row.nuts_code, row.region_mapping_status) == ("NO081", "low_confidence")
    assert row.region_mapping_method == "nav_feed_entry_municipal_nuts3"
    assert row.occupation_mapping_status == "not_present"
    assert row.number_of_vacancies == 1


@respx.mock
def test_a_content_masked_active_detail_falls_back_to_the_feed_event(
    reference_dir: Path,
) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(
            200, json=feed_page([feed_item("a", municipal="TROMSØ")], next_id=None)
        )
    )
    respx.get(f"{NAV_BASE}/api/v1/feedentry/a").mock(
        return_value=httpx.Response(200, json=ad_detail("a", masked=True))
    )
    collector = make_collector(reference_dir, max_details=5)
    row = collect(collector)[0]
    assert collector.details_masked == 1
    assert row.first_published is None
    assert (row.nuts_code, row.region_mapping_status) == ("NO072", "low_confidence")
    assert row.occupation_mapping_status == "not_present"


@respx.mock
def test_a_detail_that_is_no_longer_served_is_counted_not_fatal(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id=None))
    )
    respx.get(f"{NAV_BASE}/api/v1/feedentry/a").mock(return_value=httpx.Response(404, text=""))
    collector = make_collector(reference_dir, max_details=5)
    rows = collect(collector)
    assert len(rows) == 1
    assert collector.details_missing == 1
    assert rows[0].first_published is None


@respx.mock
def test_a_detail_that_keeps_failing_with_5xx_is_skipped_not_fatal(reference_dir: Path) -> None:
    """Details are optional enrichment; a flaky host must not void a whole sweep."""
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(
            200, json=feed_page([feed_item("a"), feed_item("b")], next_id=None)
        )
    )
    respx.get(f"{NAV_BASE}/api/v1/feedentry/a").mock(return_value=httpx.Response(500, text="boom"))
    respx.get(f"{NAV_BASE}/api/v1/feedentry/b").mock(
        return_value=httpx.Response(200, json=ad_detail("b"))
    )
    policy = RetryPolicy(max_attempts=2, base_delay=0.0, jitter=0.0)
    collector = make_collector(reference_dir, max_details=5, policy=policy)
    rows = collect(collector)
    assert len(rows) == 2
    assert collector.details_failed == 1
    assert collector.details_with_content == 1
    assert sum(1 for row in rows if row.esco_occupation_uri) == 1


@respx.mock
def test_a_non_404_4xx_on_a_detail_is_still_fatal(reference_dir: Path) -> None:
    """A 403 is a permission signal, not a hiccup: stop rather than collect on."""
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id=None))
    )
    respx.get(f"{NAV_BASE}/api/v1/feedentry/a").mock(return_value=httpx.Response(403, text=""))
    with pytest.raises(httpx.HTTPStatusError):
        collect(make_collector(reference_dir, max_details=5))


@respx.mock
def test_the_detail_budget_bounds_the_requests_but_not_the_rows(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    items = [feed_item(f"ad-{index}") for index in range(6)]
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page(items, next_id=None))
    )
    for index in range(6):
        respx.get(f"{NAV_BASE}/api/v1/feedentry/ad-{index}").mock(
            return_value=httpx.Response(200, json=ad_detail(f"ad-{index}"))
        )
    collector = make_collector(reference_dir, max_details=2)
    rows = collect(collector)
    assert len(rows) == 6
    assert collector.detail_requests == 2
    assert sum(1 for row in rows if row.esco_occupation_uri) == 2
    assert sum(1 for row in rows if row.occupation_mapping_status == "not_present") == 4


# ---------------------------------------------------------------------------
# Region resolution end to end
# ---------------------------------------------------------------------------


@respx.mock
def test_municipality_resolves_when_the_county_is_missing(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id=None))
    )
    respx.get(f"{NAV_BASE}/api/v1/feedentry/a").mock(
        return_value=httpx.Response(200, json=ad_detail("a", county=None, municipal="BERGEN"))
    )
    row = collect(make_collector(reference_dir, max_details=5))[0]
    assert (row.nuts_code, row.region_mapping_status) == ("NO0A2", "mapped")
    assert row.region_mapping_method == "nav_worklocation_municipal_nuts3"


@respx.mock
def test_an_unknown_municipality_stays_unmapped_and_is_never_forced(reference_dir: Path) -> None:
    """The live feed emits non-kommune strings such as ``"?"`` and ``"ÅMOT"``.

    ``"?"`` is NAV's own placeholder: a municipality field *was* sent, it just
    does not name a municipality, so it is ``unmapped`` rather than
    ``not_present``.
    """
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(
            200,
            json=feed_page(
                [feed_item("a", municipal="?"), feed_item("b", municipal="ÅMOT")], next_id=None
            ),
        )
    )
    rows = collect(make_collector(reference_dir, max_details=0))
    assert {row.region_mapping_status for row in rows} == {"unmapped"}
    assert {row.region_mapping_method for row in rows} == {"nav_region_name_unknown"}
    assert all(row.nuts_code is None for row in rows)


@respx.mock
def test_a_workplace_outside_norway_is_unmapped(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(
            200, json=feed_page([feed_item("a", municipal="")], next_id=None)
        )
    )
    respx.get(f"{NAV_BASE}/api/v1/feedentry/a").mock(
        return_value=httpx.Response(
            200,
            json=ad_detail("a", country="SVERIGE", county="VÄSTRA GÖTALAND", municipal="GÖTEBORG"),
        )
    )
    row = collect(make_collector(reference_dir, max_details=5))[0]
    assert row.region_mapping_status == "unmapped"
    assert row.region_mapping_method == "nav_worklocation_foreign_country"
    assert row.nuts_code is None


@respx.mock
def test_locations_in_different_regions_are_ambiguous(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id=None))
    )
    detail = ad_detail("a")
    detail["ad_content"]["workLocations"] = [
        {"country": "NORGE", "county": "VESTLAND", "municipal": "BERGEN"},
        {"country": "NORGE", "county": "OSLO", "municipal": "OSLO"},
    ]
    respx.get(f"{NAV_BASE}/api/v1/feedentry/a").mock(return_value=httpx.Response(200, json=detail))
    row = collect(make_collector(reference_dir, max_details=5))[0]
    assert row.region_mapping_status == "ambiguous"
    assert row.nuts_code in {"NO081", "NO0A2"}


@respx.mock
def test_a_name_shared_by_two_counties_is_ambiguous_without_a_code(reference_dir: Path) -> None:
    """``HERØY`` exists in Møre og Romsdal and in Nordland; guessing is refused."""
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(
            200, json=feed_page([feed_item("a", municipal="HERØY")], next_id=None)
        )
    )
    row = collect(make_collector(reference_dir, max_details=0))[0]
    assert row.region_mapping_status == "ambiguous"
    assert row.nuts_code is None


@respx.mock
def test_no_region_signal_at_all_is_not_present(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(
            200, json=feed_page([feed_item("a", municipal="")], next_id=None)
        )
    )
    row = collect(make_collector(reference_dir, max_details=0))[0]
    assert row.region_mapping_status == "not_present"
    assert row.region_mapping_method == "not_available"


# ---------------------------------------------------------------------------
# SAFE_FIELDS and PII isolation
# ---------------------------------------------------------------------------


@respx.mock
def test_record_shape_is_exactly_the_allowlist(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("a")], next_id=None))
    )
    respx.get(f"{NAV_BASE}/api/v1/feedentry/a").mock(
        return_value=httpx.Response(200, json=ad_detail("a"))
    )
    row = collect(make_collector(reference_dir, max_details=5))[0]
    dumped = row.model_dump_ndjson()
    assert dumped["source"] == "nav"
    assert dumped["country"] == "NO"
    assert dumped["lang"] == dumped["source_language"] == "no"
    assert dumped["nuts_version"] == "NUTS-2024"
    assert dumped["esco_version"] == "1.2.1"
    assert dumped["jobtech_taxonomy_version"] == ""
    assert dumped["scope_id"] == "no-all-events"


@respx.mock
def test_pii_never_reaches_the_record_or_the_raw_payload(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(200, json=feed_page([feed_item("private-uuid")], next_id=None))
    )
    respx.get(f"{NAV_BASE}/api/v1/feedentry/private-uuid").mock(
        return_value=httpx.Response(200, json=ad_detail("private-uuid"))
    )
    collector = make_collector(reference_dir, max_details=5)

    async def go() -> tuple[list[str], list[str]]:
        async with collector:
            raws = [raw async for raw in collector.fetch()]
            records = [collector.normalize(collector.parse(raw)) for raw in raws]
        return (
            [json.dumps(raw.payload, ensure_ascii=False) for raw in raws],
            [json.dumps(record.model_dump_ndjson(), ensure_ascii=False) for record in records],
        )

    raw_blobs, record_blobs = run(go())
    forbidden = (
        "Privat Kontaktperson",
        "privat@example.invalid",
        "99988777",
        "999888777",
        "Private Employer AS",
        "Private Job Title",
        "https://apply.example.invalid/1",
        "https://source.example.invalid/1",
        "employer.example.invalid",
        "Privatvegen 35",
        "5003",
        "private-uuid",
        "Privat omtale",
        "butikkmedarbeider",
    )
    for blob in [*raw_blobs, *record_blobs]:
        for token in forbidden:
            assert token not in blob, f"{token} leaked into {blob[:160]}"
    assert "postalCode" not in raw_blobs[0]
    assert "contactList" not in raw_blobs[0]


# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------


@respx.mock
def test_429_is_retried_honoring_retry_after(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json=feed_page([feed_item("a")], next_id=None)),
        ]
    )
    policy = RetryPolicy(max_attempts=3, base_delay=0.0, jitter=0.0)
    rows = collect(make_collector(reference_dir, max_details=0, policy=policy))
    assert len(rows) == 1


@respx.mock
def test_a_transport_error_is_retried(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        side_effect=[
            httpx.ConnectError("boom"),
            httpx.Response(200, json=feed_page([feed_item("a")], next_id=None)),
        ]
    )
    policy = RetryPolicy(max_attempts=3, base_delay=0.0, jitter=0.0)
    assert len(collect(make_collector(reference_dir, max_details=0, policy=policy))) == 1


@respx.mock
def test_a_feed_page_missing_the_feed_entry_fails_loudly(reference_dir: Path) -> None:
    """A schema drift must not silently drop ads."""
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [{"id": "x", "url": "/api/v1/feedentry/x", "date_modified": None}],
                "next_url": None,
                "next_id": None,
            },
        )
    )
    with pytest.raises(ValueError, match="feed_entry"):
        collect(make_collector(reference_dir, max_details=0))


@respx.mock
def test_a_500_on_the_feed_is_fatal_after_retries(reference_dir: Path) -> None:
    mock_robots(respx.mock)
    respx.get(NAV_PUBLIC_TOKEN_URL).mock(return_value=httpx.Response(200, text=TOKEN_BODY))
    respx.get(NAV_FEED_URL).mock(return_value=httpx.Response(500, text="boom"))
    policy = RetryPolicy(max_attempts=2, base_delay=0.0, jitter=0.0)
    with pytest.raises(httpx.HTTPStatusError):
        collect(make_collector(reference_dir, max_details=0, policy=policy))


def test_a_short_hmac_key_is_refused(reference_dir: Path) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        NAVFeedCollector(
            scope_id="no-all-events",
            sweep_id="20260823T000000Z",
            observed_at=datetime(2026, 8, 23, tzinfo=UTC),
            hmac_key=b"too-short",
            reference_dir=reference_dir,
        )


def test_the_backfill_window_is_capped_at_the_six_month_ad_lifetime(reference_dir: Path) -> None:
    collector = make_collector(reference_dir, since_days=5000)
    assert collector._since_days == 190
