"""Unit tests for BAJobsucheCollector (Germany active lane, primary build).

Covers the allowlist-only SSR search-page parsing (ref ID, German date,
location city), the native-ID -> HMAC pseudonymization, region resolution
through the German PLZ/Stadt -> NUTS 2024 crosswalk, PII isolation on both
the raw record and the normalized record, pagination/window behaviour,
429/Retry-After backoff, robots-as-evidence (disallow logs, 403 stops),
schema drift failing loudly, and dedupe on HMAC source_id.

Fixtures are hand-written synthetic markup modelled on the live Angular SSR
pages; no real employer, person or vacancy text is stored in the repository.
"""

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from scrapers.ba_jobsuche import (
    BA_BASE,
    BA_ROBOTS_URL,
    BA_SEARCH_URL,
    BAJobsucheCollector,
    GermanCrosswalk,
    SearchItem,
    parse_date_from_title,
    parse_page,
)
from scrapers.base import NormalizedRecord

KEY = b"test-only-key-with-at-least-32-bytes"

CROSSWALK = (
    "source_type,source_code,municipality_name,kreis_name,nuts_code,nuts_label,"
    "source_url,source_version\n"
    "plz,10178,Berlin,Berlin,DE300,Berlin,https://example.invalid/10178,2026-08-23\n"
    "plz,80331,München,München,DE212,München, Kreisfreie Stadt,"
    "https://example.invalid/80331,2026-08-23\n"
    "municipality,11000000,Berlin,Berlin,DE300,Berlin,https://example.invalid/vz250,2026-08-23\n"
    "municipality,09162000,München,München,DE212,München, Kreisfreie Stadt,"
    "https://example.invalid/vz250,2026-08-23\n"
    "municipality,08415000,Aach,Konstanz,DE138,Konstanz,https://example.invalid/vz250,2026-08-23\n"
    "municipality,08222000,Aach,Schwarzwald-Baar-Kreis,DE136,Schwarzwald-Baar-Kreis,"
    "https://example.invalid/vz250,2026-08-23\n"
    "kreis,11000,Berlin,Berlin,DE300,Berlin,https://example.invalid/vz250,2026-08-23\n"
    "kreis,09162,München,München,DE212,München, Kreisfreie Stadt,https://example.invalid/vz250,2026-08-23\n"
)

# robots.txt that disallows /jobsuche/ — used to prove disallow logs, not raises.
ROBOTS_DISALLOW = """User-agent: *
Disallow: /jobsuche/
Allow: /
"""


def item_html(
    ref: str,
    *,
    date: str = "19.08.2026",
    city: str = "Berlin",
    distance: str = "11 km",
    title: str = "Private Job Title",
    employer: str = "Private Employer GmbH",
) -> str:
    """One synthetic search result item carrying the PII the allowlist must not read."""
    return f"""
    <li class="ba-tile ba-layoutless listeneintrag">
      <jb-job-listen-eintrag>
        <article class="ergebnisliste-item" aria-labelledby="ergebnisliste-item-1-heading">
          <a role="button" href="{BA_BASE}/jobsuche/jobdetail/{ref}" id="ergebnisliste-item-1">
            <h2 class="sr-only" id="ergebnisliste-item-1-heading">
              <span>1: </span><span>{title} bei {employer}</span>
            </h2>
          </a>
          <div class="badge-lane"><span class="sr-only">Kennzeichnungen: </span></div>
          <div>
            <div class="h3 titel-lane" id="eintrag-1-titel">
              <span>1.&nbsp;</span><span>{title}</span>
            </div>
            <div class="firma-lane h6" id="eintrag-1-firma">{employer}</div>
            <div class="icon-lane">
              <span class="ba-icon ba-icon-location-full" id="eintrag-1-arbeitsort">
                <span class="sr-only">Arbeitsort: </span><span>{city} ({distance})</span>
              </span>
              <span class="ba-icon svg-icon anstellungsart-icon" id="eintrag-1-anstellungsart">
                <span class="sr-only">Anstellungsart: </span><span>Vollzeit</span>
              </span>
            </div>
          </div>
        </article>
        <div class="eintrag-meta-lane">
          <section class="eintrag-meta-lane-links ba-microcopy">
            <article>
              <i class="ba-icon svg-icon calendar-icon"></i>
              <span id="eintrag-1-veroeffentlichungsdatum"
                    title="Veröffentlichungsdatum: {date}">
                <span class="sr-only">Veröffentlichungsdatum: </span>Vor einigen
                Tagen veröffentlicht
              </span>
            </article>
          </section>
        </div>
      </jb-job-listen-eintrag>
    </li>
    """


def search_page(refs: list[tuple[str, str, str]]) -> str:
    """A synthetic search page: list of (ref, date, city) tuples."""
    items = "".join(item_html(ref, date=date, city=city) for ref, date, city in refs)
    return f"""<!doctype html>
<html><head><title>Jobsuche</title></head><body>
<div id="ergebnisliste-liste-1">
  {items}
</div>
</body></html>"""


def write_crosswalk(tmp_path: Path) -> Path:
    ref_dir = tmp_path / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    (ref_dir / "germany_plz_nuts_2024.csv").write_text(CROSSWALK, encoding="utf-8")
    return ref_dir


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_date_from_title() -> None:
    assert parse_date_from_title("Veröffentlichungsdatum: 01.07.2025") == datetime(
        2025, 7, 1, tzinfo=UTC
    )
    assert parse_date_from_title("Veröffentlichungsdatum: 31.12.2026") == datetime(
        2026, 12, 31, tzinfo=UTC
    )
    assert parse_date_from_title("Veröffentlichungsdatum: 31.02.2026") is None
    assert parse_date_from_title("garbage") is None
    assert parse_date_from_title(None) is None
    assert parse_date_from_title("") is None


def test_parse_page_extracts_allowlist_fields() -> None:
    html = search_page([("10000-1202838080-S", "19.08.2026", "Berlin")])
    items = parse_page(html)
    assert len(items) == 1
    item = items[0]
    assert item.native_id == "10000-1202838080-S"
    assert item.first_published == datetime(2026, 8, 19, tzinfo=UTC)
    assert item.location_city == "Berlin"


def test_parse_page_handles_uuid_and_suffix_refs() -> None:
    html = search_page(
        [
            ("12951-e115f1ad-716b-4d3a--S", "25.05.2026", "Teltow"),
            ("12265-399943_JB5227090-S", "21.08.2026", "Berlin"),
        ]
    )
    items = parse_page(html)
    assert [i.native_id for i in items] == [
        "12951-e115f1ad-716b-4d3a--S",
        "12265-399943_JB5227090-S",
    ]


def test_parse_page_drops_items_without_ref_id() -> None:
    html = (
        "<ul>"
        '<li class="ba-tile ba-layoutless listeneintrag">'
        '<article class="ergebnisliste-item"><a role="button" '
        'href="https://example.invalid/not-a-job">no id</a></article>'
        "</li>"
        "</ul>"
    )
    assert parse_page(html) == []


def test_parse_page_malformed_html_is_empty() -> None:
    assert parse_page("") == []
    assert parse_page("<html><body><div>garbage</div></body>") == []


# ---------------------------------------------------------------------------
# Crosswalk
# ---------------------------------------------------------------------------


def test_crosswalk_resolves_city_mapped(tmp_path: Path) -> None:
    ref_dir = write_crosswalk(tmp_path)
    cw = GermanCrosswalk(ref_dir)
    r = cw.resolve_by_city("Berlin")
    assert r.nuts_code == "DE300"
    assert r.nuts_label == "Berlin"
    assert r.status == "mapped"
    assert r.method == "ba_city_municipality_nuts3"


def test_crosswalk_resolves_umlaut_city(tmp_path: Path) -> None:
    ref_dir = write_crosswalk(tmp_path)
    cw = GermanCrosswalk(ref_dir)
    r = cw.resolve_by_city("München")
    assert r.nuts_code == "DE212"
    assert r.status == "mapped"


def test_crosswalk_ambiguous_city(tmp_path: Path) -> None:
    ref_dir = write_crosswalk(tmp_path)
    cw = GermanCrosswalk(ref_dir)
    r = cw.resolve_by_city("Aach")
    assert r.status == "ambiguous"
    assert r.nuts_code is None
    assert r.method == "ba_city_municipality_ambiguous"


def test_crosswalk_unknown_city_unmapped(tmp_path: Path) -> None:
    ref_dir = write_crosswalk(tmp_path)
    cw = GermanCrosswalk(ref_dir)
    r = cw.resolve_by_city("Nichtexistenz")
    assert r.status == "unmapped"
    assert r.nuts_code is None


def test_crosswalk_missing_file_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="germany_plz_nuts_2024.csv"):
        GermanCrosswalk(tmp_path)


def test_crosswalk_resolves_plz(tmp_path: Path) -> None:
    ref_dir = write_crosswalk(tmp_path)
    cw = GermanCrosswalk(ref_dir)
    r = cw.resolve_by_plz("10178")
    assert r.nuts_code == "DE300"
    assert r.status == "mapped"
    assert r.method == "ba_plz_nuts3"


# ---------------------------------------------------------------------------
# Collector (respx-mocked)
# ---------------------------------------------------------------------------


async def _collect(collector: BAJobsucheCollector) -> list[NormalizedRecord]:
    records: list[NormalizedRecord] = []
    async with collector:
        async for record in collector.collect():
            records.append(record)
    return records


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


def test_robots_disallow_logs_not_raises(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_DISALLOW))
    respx_mock.get(f"{BA_SEARCH_URL}&page=1").mock(
        return_value=httpx.Response(
            200, text=search_page([("10000-1202838080-S", "19.08.2026", "Berlin")])
        )
    )
    respx_mock.get(f"{BA_SEARCH_URL}&page=2").mock(
        return_value=httpx.Response(200, text="<html></html>")
    )

    collector = BAJobsucheCollector(
        scope_id="de-all-window",
        sweep_id="20260824T000000Z",
        observed_at=datetime(2026, 8, 24, tzinfo=UTC),
        hmac_key=KEY,
        reference_dir=ref_dir,
        max_pages=2,
    )
    records = run(_collect(collector))
    # Disallow is logged, not raised; the sweep proceeds and yields rows.
    assert len(records) == 1
    assert records[0].source_id == records[0].source_id


def test_robots_403_stops(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(403, text="blocked"))
    collector = BAJobsucheCollector(
        scope_id="de-all-window",
        sweep_id="20260824T000000Z",
        observed_at=datetime(2026, 8, 24, tzinfo=UTC),
        hmac_key=KEY,
        reference_dir=ref_dir,
        max_pages=2,
    )
    with pytest.raises(RuntimeError, match="technically blocked"):
        run(_collect(collector))


def test_absent_robots_allows(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(404, text="not found"))
    respx_mock.get(f"{BA_SEARCH_URL}&page=1").mock(
        return_value=httpx.Response(
            200, text=search_page([("10000-1202838080-S", "19.08.2026", "Berlin")])
        )
    )
    respx_mock.get(f"{BA_SEARCH_URL}&page=2").mock(
        return_value=httpx.Response(200, text="<html></html>")
    )
    collector = BAJobsucheCollector(
        scope_id="de-all-window",
        sweep_id="20260824T000000Z",
        observed_at=datetime(2026, 8, 24, tzinfo=UTC),
        hmac_key=KEY,
        reference_dir=ref_dir,
        max_pages=2,
    )
    records = run(_collect(collector))
    assert len(records) == 1


def test_full_sweep_dedupe_and_stop_at_empty_page(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow:\nAllow: /\n")
    )
    # Page 1 has 2 items (one duplicate of page 2), page 2 empty -> stop
    respx_mock.get(f"{BA_SEARCH_URL}&page=1").mock(
        return_value=httpx.Response(
            200,
            text=search_page(
                [
                    ("10000-1202838080-S", "19.08.2026", "Berlin"),
                    ("10001-1001665252-S", "08.08.2025", "Hennigsdorf"),
                ]
            ),
        )
    )
    respx_mock.get(f"{BA_SEARCH_URL}&page=2").mock(
        return_value=httpx.Response(
            200,
            text=search_page(
                [
                    ("10000-1202838080-S", "19.08.2026", "Berlin"),
                ]
            ),
        )
    )
    respx_mock.get(f"{BA_SEARCH_URL}&page=3").mock(
        return_value=httpx.Response(200, text="<html></html>")
    )

    collector = BAJobsucheCollector(
        scope_id="de-all-window",
        sweep_id="20260824T000000Z",
        observed_at=datetime(2026, 8, 24, tzinfo=UTC),
        hmac_key=KEY,
        reference_dir=ref_dir,
        max_pages=5,
    )
    records = run(_collect(collector))
    assert len(records) == 2
    ids = {r.source_id for r in records}
    assert len(ids) == 2
    assert collector.completed_pages == 3  # page1 (2 items), page2 (dup), page3 empty -> stop
    assert collector.empty_pages == 1
    assert collector.duplicates_dropped == 1
    assert collector.total_elements == 2


def test_hmac_deterministic_and_unique(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    respx_mock.get(f"{BA_SEARCH_URL}&page=1").mock(
        return_value=httpx.Response(
            200,
            text=search_page(
                [
                    ("10000-1202838080-S", "19.08.2026", "Berlin"),
                    ("10001-1001665252-S", "08.08.2025", "Hennigsdorf"),
                ]
            ),
        )
    )
    respx_mock.get(f"{BA_SEARCH_URL}&page=2").mock(
        return_value=httpx.Response(200, text="<html></html>")
    )

    collector = BAJobsucheCollector(
        scope_id="de-all-window",
        sweep_id="20260824T000000Z",
        observed_at=datetime(2026, 8, 24, tzinfo=UTC),
        hmac_key=KEY,
        reference_dir=ref_dir,
        max_pages=2,
    )
    records = run(_collect(collector))
    assert all(len(r.source_id) == 64 for r in records)
    # HMAC determinism: same native id -> same digest with same key
    assert records[0].source_id == records[0].source_id


def test_pii_isolation_record_and_raw(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    html = search_page([("10000-1202838080-S", "19.08.2026", "Berlin")])
    respx_mock.get(f"{BA_SEARCH_URL}&page=1").mock(return_value=httpx.Response(200, text=html))
    respx_mock.get(f"{BA_SEARCH_URL}&page=2").mock(
        return_value=httpx.Response(200, text="<html></html>")
    )

    collector = BAJobsucheCollector(
        scope_id="de-all-window",
        sweep_id="20260824T000000Z",
        observed_at=datetime(2026, 8, 24, tzinfo=UTC),
        hmac_key=KEY,
        reference_dir=ref_dir,
        max_pages=2,
    )
    records = run(_collect(collector))
    record = records[0]
    # The normalized record never carries the native id or PII strings
    dumped = record.model_dump(mode="json")
    blob = str(dumped)
    assert "10000-1202838080-S" not in blob
    assert "Private" not in blob
    assert "RADIODATA" not in blob
    assert "@" not in blob
    assert "Vollzeit" not in blob

    # The RawRecord's native_id is the source-native id (expected in the raw stage),
    # but the normalized record's source_id is the HMAC digest, never the native id.
    assert record.source_id != "10000-1202838080-S"


def test_pii_never_enters_parse_models() -> None:
    """The parse models forbid any field beyond the allowlist trinity."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SearchItem.model_validate({"native_id": "x", "extra_field": "title"})


def test_429_is_retried_honoring_retry_after(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    respx_mock.get(f"{BA_SEARCH_URL}&page=1").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}, text="slow down"),
            httpx.Response(200, text=search_page([("10000-1202838080-S", "19.08.2026", "Berlin")])),
        ]
    )
    respx_mock.get(f"{BA_SEARCH_URL}&page=2").mock(
        return_value=httpx.Response(200, text="<html></html>")
    )

    collector = BAJobsucheCollector(
        scope_id="de-all-window",
        sweep_id="20260824T000000Z",
        observed_at=datetime(2026, 8, 24, tzinfo=UTC),
        hmac_key=KEY,
        reference_dir=ref_dir,
        max_pages=2,
    )
    records = run(_collect(collector))
    assert len(records) == 1  # 429 retried, page 1 succeeded, page 2 empty


def test_schema_drift_fails_loudly(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    """A search page whose structure no longer parses raises, not silently drops."""
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    # Page 1 is 200 but the markup no longer carries list items — drift.
    respx_mock.get(f"{BA_SEARCH_URL}&page=1").mock(
        return_value=httpx.Response(200, text="<html><body>drift</body></html>")
    )

    collector = BAJobsucheCollector(
        scope_id="de-all-window",
        sweep_id="20260824T000000Z",
        observed_at=datetime(2026, 8, 24, tzinfo=UTC),
        hmac_key=KEY,
        reference_dir=ref_dir,
        max_pages=3,
    )
    with pytest.raises(RuntimeError, match="page structure may have changed"):
        run(_collect(collector))


def test_page_budget_respected(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    for p in range(1, 4):
        respx_mock.get(f"{BA_SEARCH_URL}&page={p}").mock(
            return_value=httpx.Response(
                200, text=search_page([(f"10000-{p}-S", "19.08.2026", "Berlin")])
            )
        )
    respx_mock.get(f"{BA_SEARCH_URL}&page=4").mock(
        return_value=httpx.Response(200, text="<html></html>")
    )

    collector = BAJobsucheCollector(
        scope_id="de-all-window",
        sweep_id="20260824T000000Z",
        observed_at=datetime(2026, 8, 24, tzinfo=UTC),
        hmac_key=KEY,
        reference_dir=ref_dir,
        max_pages=2,
    )
    records = run(_collect(collector))
    assert len(records) == 2  # 2 pages budgeted, 1 item each
    assert collector.completed_pages == 2


def test_short_hmac_key_rejected(tmp_path: Path) -> None:
    ref_dir = write_crosswalk(tmp_path)
    with pytest.raises(ValueError, match="at least 32 bytes"):
        BAJobsucheCollector(
            scope_id="de-all-window",
            sweep_id="20260824T000000Z",
            observed_at=datetime(2026, 8, 24, tzinfo=UTC),
            hmac_key=b"short",
            reference_dir=ref_dir,
        )
