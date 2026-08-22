"""Unit tests for VDABCollector (Increment 5) against mocked HTML fixtures.

Covers the robots.txt gate (the increment's core compliance guarantee: the
robots-disallowed ``/api/vindeenjob/`` must be impossible to request), sitemap
discovery and breadth ordering, allowlist-only tile parsing, the Dutch date
table, cross-page dedupe on the HMAC digest, the postcode -> NUTS 2024
crosswalk, PII isolation, 429 backoff honoring ``Retry-After``, malformed
markup, and the "no pagination parameters" contract.

Fixtures are hand-written synthetic markup modelled on the live page structure;
no real employer, person or vacancy text is stored in the repository.
"""

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from scrapers.base import NormalizedRecord
from scrapers.retry import RetryPolicy
from scrapers.vdab import (
    DUTCH_MONTHS,
    VDAB_BASE,
    VDAB_FORBIDDEN_API_PATH,
    VDAB_KEYWORD_SITEMAP_URL,
    VDAB_REFERENCE_FILE,
    VDAB_ROBOTS_URL,
    RobotsDisallowedError,
    VDABCollector,
    VDABCrosswalk,
    crosswalk_reference_hashes,
    landing_postcode,
    order_by_postcode_breadth,
    parse_dutch_date,
    parse_landing_page,
    sitemap_locations,
)

KEY = b"test-only-key-with-at-least-32-bytes"

HEADER = "source_type,source_code,nuts_code,nuts_label,source_url,source_version\n"
ROWS = (
    "postcode,9000,BE234,Arr. Gent,https://example.invalid/9000,2026-08-22\n"
    "postcode,2000,BE211,Arr. Antwerpen,https://example.invalid/2000,2026-08-22\n"
    "postcode,3000,BE242,Arr. Leuven,https://example.invalid/3000,2026-08-22\n"
    "postcode,8000,BE251,Arr. Brugge,https://example.invalid/8000,2026-08-22\n"
)

# The live robots.txt shape that matters: sitemaps advertised, the Angular API
# and the private surfaces disallowed, no Crawl-Delay for *.
ROBOTS_TXT = """User-agent: Baiduspider*
Disallow: /

User-agent: *
Disallow: /api/vindeenjob/
Disallow: /vacatures/
Disallow: /include/vacature/
Disallow: /zoeken/
Disallow: /tv-zoeken/
Disallow: /vindeenjob/prive/
Disallow: /mijnvdab/
Disallow: /vac/
Disallow: /prive/

Sitemap: https://www.vdab.be/sitemap.xml
Sitemap: https://www.vdab.be/vindeenjob/jobs/nc/sitemap/sitemap.xml
Sitemap: https://www.vdab.be/sitemap/vindeenjob/vacatures/index.xml
"""

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://www.vdab.be/vindeenjob/jobs/nc/sitemap/keyword-0.xml</loc></sitemap>
  <sitemap><loc>https://www.vdab.be/vindeenjob/jobs/nc/sitemap/keyword-1.xml</loc></sitemap>
</sitemapindex>
"""


def keyword_sitemap(urls: list[str]) -> str:
    entries = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + entries + "</urlset>"
    )


def tile(
    vacancy_id: str,
    *,
    online_since: str = "Online sinds  15 aug. 2026",
    employer: str = "Private Employer NV",
    title: str = "Private Job Title",
    city: str = "GENT",
    description: str = "Private omschrijving met contactgegevens 0470 12 34 56.",
    href: str | None = None,
) -> str:
    """One synthetic tile carrying the PII the allowlist must never let through."""
    link = (
        href
        if href is not None
        else (
            f"{VDAB_BASE}/vindeenjob/vacatures/{vacancy_id}/private-slug-{vacancy_id}"
            "?trefwoord=x&source=trefwoordpagina&sort=standaard&medium=verbolia"
        )
    )
    return f"""
    <div class="product-tile">
      <a class="product-link" href="{link}">
        <div class="product-wrapper-tile">
          <div class="product-info">
            <h2 class="product-title">{title}</h2>
            <div class="location-job"><strong>{employer}</strong> in <strong>{city}</strong></div>
            <span class="type-contract">Vaste jobs</span>
          </div>
          <img class="company-logo" alt="company logo"
               src="https://cdn.example.invalid/bedrijven/3769/logo.jpg"/>
        </div>
        <div class="job-type"><span class="online-sinds">{online_since}</span></div>
        <div class="product-description">{description}</div>
      </a>
    </div>
    """


def landing_html(tiles: list[str], *, advertised: int = 1627) -> str:
    return f"""<!DOCTYPE html><html lang="nl"><head><title>jobs</title></head><body>
    <main class="main-content"><div class="container"><div class="products-section">
    <div class="product-container">
      <div class="sorted-jobs">
        <div class="numbers-job"><strong>{advertised}</strong><span>jobs gevonden</span></div>
      </div>
      <div class="product-wrapper">{"".join(tiles)}</div>
    </div></div></div></main></body></html>"""


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


@pytest.fixture
def reference_dir(tmp_path: Path) -> Path:
    (tmp_path / VDAB_REFERENCE_FILE).write_text(HEADER + ROWS, encoding="utf-8")
    return tmp_path


def make_collector(
    reference_dir: Path,
    *,
    max_pages: int | None = None,
    landing_pages: list[str] | None = None,
    flemish_only: bool = True,
    policy: RetryPolicy | None = None,
) -> VDABCollector:
    return VDABCollector(
        scope_id="be-flanders-all-active",
        sweep_id="20260822T000000Z",
        observed_at=datetime(2026, 8, 22, tzinfo=UTC),
        hmac_key=KEY,
        reference_dir=reference_dir,
        max_pages=max_pages,
        landing_pages=landing_pages,
        flemish_only=flemish_only,
        pacing_interval=0.0,
        policy=policy,
    )


def collect(collector: VDABCollector) -> list[NormalizedRecord]:
    async def go() -> list[NormalizedRecord]:
        async with collector:
            return [record async for record in collector.collect()]

    return run(go())


# ---------------------------------------------------------------------------
# robots.txt gate — the compliance guarantee of this increment
# ---------------------------------------------------------------------------


def test_robots_is_fetched_before_any_other_url(reference_dir: Path) -> None:
    with respx.mock:
        robots = respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        page = respx.get(f"{VDAB_BASE}/vindeenjob/jobs/9000-gent").mock(
            return_value=httpx.Response(200, text=landing_html([tile("1")]))
        )
        collector = make_collector(
            reference_dir, landing_pages=[f"{VDAB_BASE}/vindeenjob/jobs/9000-gent"]
        )
        collect(collector)
        assert robots.called
        assert page.called
        # robots.txt is request #1 of the sweep.
        assert respx.calls[0].request.url.path == "/robots.txt"


def test_disallowed_api_path_raises(reference_dir: Path) -> None:
    """The Angular JSON API is robots-disallowed: asking for it must fail loudly."""
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        collector = make_collector(reference_dir, landing_pages=[])
        run(collector._load_robots())
        with pytest.raises(RobotsDisallowedError, match="disallows"):
            collector.assert_allowed(f"{VDAB_BASE}{VDAB_FORBIDDEN_API_PATH}vacatures/zoek")
        for path in (
            "/vacatures/",
            "/include/vacature/",
            "/zoeken/",
            "/tv-zoeken/",
            "/vindeenjob/prive/",
            "/mijnvdab/",
            "/vac/",
            "/prive/",
        ):
            with pytest.raises(RobotsDisallowedError):
                collector.assert_allowed(VDAB_BASE + path)
        # The permitted surfaces stay permitted.
        collector.assert_allowed(f"{VDAB_BASE}/vindeenjob/jobs/9000-gent")
        collector.assert_allowed(VDAB_KEYWORD_SITEMAP_URL)
        run(collector.aclose())


def test_sweep_never_requests_the_disallowed_api(reference_dir: Path) -> None:
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(VDAB_KEYWORD_SITEMAP_URL).mock(
            return_value=httpx.Response(200, text=SITEMAP_INDEX)
        )
        respx.get(f"{VDAB_BASE}/vindeenjob/jobs/nc/sitemap/keyword-0.xml").mock(
            return_value=httpx.Response(
                200,
                text=keyword_sitemap(
                    [
                        f"{VDAB_BASE}/vindeenjob/jobs/9000-gent",
                        f"{VDAB_BASE}/vindeenjob/jobs/2000-antwerpen",
                    ]
                ),
            )
        )
        respx.get(url__regex=r".*/vindeenjob/jobs/(9000-gent|2000-antwerpen)$").mock(
            return_value=httpx.Response(200, text=landing_html([tile("11"), tile("12")]))
        )
        rows = collect(make_collector(reference_dir, max_pages=2))
        assert len(rows) == 2
        requested = [call.request.url.path for call in respx.calls]
        assert not any(path.startswith(VDAB_FORBIDDEN_API_PATH) for path in requested)
        assert not any("/rest/vindeenjob" in path for path in requested)


def test_assert_allowed_requires_loaded_robots(reference_dir: Path) -> None:
    collector = make_collector(reference_dir, landing_pages=[])
    with pytest.raises(RobotsDisallowedError, match="not loaded"):
        collector.assert_allowed(f"{VDAB_BASE}/vindeenjob/jobs/9000-gent")
    run(collector.aclose())


def test_absent_robots_allows_the_landing_pages(reference_dir: Path) -> None:
    """A 404 robots.txt means nothing is disallowed (RobotsRule contract)."""
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(404, text="not found"))
        respx.get(f"{VDAB_BASE}/vindeenjob/jobs/9000-gent").mock(
            return_value=httpx.Response(200, text=landing_html([tile("1")]))
        )
        rows = collect(
            make_collector(reference_dir, landing_pages=[f"{VDAB_BASE}/vindeenjob/jobs/9000-gent"])
        )
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_sitemap_locations_reads_index_and_urlset() -> None:
    assert sitemap_locations(SITEMAP_INDEX) == [
        f"{VDAB_BASE}/vindeenjob/jobs/nc/sitemap/keyword-0.xml",
        f"{VDAB_BASE}/vindeenjob/jobs/nc/sitemap/keyword-1.xml",
    ]
    assert sitemap_locations(keyword_sitemap(["https://a.invalid/x"])) == ["https://a.invalid/x"]
    assert sitemap_locations("not xml at all") == []


def test_landing_postcode_extraction() -> None:
    assert landing_postcode(f"{VDAB_BASE}/vindeenjob/jobs/9000-gent") == "9000"
    assert landing_postcode(f"{VDAB_BASE}/vindeenjob/jobs/1020-laken-brussel-stad") == "1020"
    assert landing_postcode(f"{VDAB_BASE}/vindeenjob/jobs/9000-gent/") == "9000"
    assert landing_postcode(f"{VDAB_BASE}/vindeenjob/jobs/9000-gent?x=1") == "9000"
    # Keyword pages without a postcode prefix carry no region signal.
    assert landing_postcode(f"{VDAB_BASE}/vindeenjob/jobs/verpleegkundige") is None
    assert landing_postcode(f"{VDAB_BASE}/vindeenjob/jobs/0612-sinterklaas") is None
    assert landing_postcode(f"{VDAB_BASE}/vindeenjob/vacatures/74387619/slug") is None


def test_discovery_filters_to_flemish_postcodes(reference_dir: Path) -> None:
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(VDAB_KEYWORD_SITEMAP_URL).mock(
            return_value=httpx.Response(200, text=SITEMAP_INDEX)
        )
        respx.get(f"{VDAB_BASE}/vindeenjob/jobs/nc/sitemap/keyword-0.xml").mock(
            return_value=httpx.Response(
                200,
                text=keyword_sitemap(
                    [
                        f"{VDAB_BASE}/vindeenjob/jobs/9000-gent",
                        f"{VDAB_BASE}/vindeenjob/jobs/1000-brussel",  # not in the register
                        f"{VDAB_BASE}/vindeenjob/jobs/1011-amsterdam",  # foreign
                        f"{VDAB_BASE}/vindeenjob/jobs/verpleegkundige",  # no postcode
                        f"{VDAB_BASE}/vindeenjob/jobs/2000-antwerpen",
                    ]
                ),
            )
        )
        respx.get(f"{VDAB_BASE}/vindeenjob/jobs/nc/sitemap/keyword-1.xml").mock(
            return_value=httpx.Response(200, text=keyword_sitemap([]))
        )
        collector = make_collector(reference_dir, max_pages=50)

        async def go() -> list[str]:
            async with collector:
                await collector._load_robots()
                return await collector.discover_landing_pages()

        pages = run(go())
        assert pages == [
            f"{VDAB_BASE}/vindeenjob/jobs/2000-antwerpen",
            f"{VDAB_BASE}/vindeenjob/jobs/9000-gent",
        ]
        assert collector.landing_pages_available == 2


def test_discovery_stops_reading_children_once_the_budget_is_covered(
    reference_dir: Path,
) -> None:
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(VDAB_KEYWORD_SITEMAP_URL).mock(
            return_value=httpx.Response(200, text=SITEMAP_INDEX)
        )
        first = respx.get(f"{VDAB_BASE}/vindeenjob/jobs/nc/sitemap/keyword-0.xml").mock(
            return_value=httpx.Response(
                200,
                text=keyword_sitemap(
                    [
                        f"{VDAB_BASE}/vindeenjob/jobs/9000-gent",
                        f"{VDAB_BASE}/vindeenjob/jobs/2000-antwerpen",
                    ]
                ),
            )
        )
        second = respx.get(f"{VDAB_BASE}/vindeenjob/jobs/nc/sitemap/keyword-1.xml").mock(
            return_value=httpx.Response(200, text=keyword_sitemap([]))
        )
        collector = make_collector(reference_dir, max_pages=1)

        async def go() -> list[str]:
            async with collector:
                await collector._load_robots()
                return await collector.discover_landing_pages()

        run(go())
        assert first.called
        assert not second.called


def test_breadth_ordering_puts_one_page_per_postcode_first() -> None:
    pages = [
        f"{VDAB_BASE}/vindeenjob/jobs/9000-gent",
        f"{VDAB_BASE}/vindeenjob/jobs/9000-gent-deeltijds",
        f"{VDAB_BASE}/vindeenjob/jobs/9000-gent-provincie",
        f"{VDAB_BASE}/vindeenjob/jobs/2000-antwerpen",
        f"{VDAB_BASE}/vindeenjob/jobs/2000-antwerpen-deeltijds",
        f"{VDAB_BASE}/vindeenjob/jobs/3000-leuven",
    ]
    assert order_by_postcode_breadth(pages) == [
        f"{VDAB_BASE}/vindeenjob/jobs/2000-antwerpen",
        f"{VDAB_BASE}/vindeenjob/jobs/3000-leuven",
        f"{VDAB_BASE}/vindeenjob/jobs/9000-gent",
        f"{VDAB_BASE}/vindeenjob/jobs/2000-antwerpen-deeltijds",
        f"{VDAB_BASE}/vindeenjob/jobs/9000-gent-deeltijds",
        f"{VDAB_BASE}/vindeenjob/jobs/9000-gent-provincie",
    ]
    assert order_by_postcode_breadth([]) == []


# ---------------------------------------------------------------------------
# Tile parsing (allowlist-only)
# ---------------------------------------------------------------------------


def test_parse_landing_page_reads_only_id_and_date() -> None:
    page = parse_landing_page(
        landing_html([tile("74387619"), tile("74287473", online_since="Online sinds 1 jul. 2026")]),
        postcode="9000",
    )
    assert page.postcode == "9000"
    assert page.advertised_total == 1627
    assert [t.native_id for t in page.tiles] == ["74387619", "74287473"]
    assert page.tiles[0].online_since == "Online sinds 15 aug. 2026"
    dumped = page.model_dump()
    # No title, employer, city, description, logo or link anywhere in the parse.
    for token in ("Private Employer NV", "Private Job Title", "GENT", "omschrijving", "logo.jpg"):
        assert token not in str(dumped)


def test_tiles_without_a_resolvable_id_are_counted_not_guessed() -> None:
    broken = """
    <div class="product-tile">
      <a class="product-link" href="/vindeenjob/vacatures/no-id-here">
        <h2 class="product-title">Broken</h2>
        <span class="online-sinds">Online sinds 15 aug. 2026</span>
      </a>
    </div>
    """
    no_link = '<div class="product-tile"><h2 class="product-title">No link</h2></div>'
    page = parse_landing_page(landing_html([tile("1"), broken, no_link]))
    assert [t.native_id for t in page.tiles] == ["1"]
    assert page.tiles_without_id == 2


def test_tile_without_a_date_yields_no_first_published() -> None:
    without_date = """
    <div class="product-tile">
      <a class="product-link" href="/vindeenjob/vacatures/42/slug"></a>
    </div>
    """
    page = parse_landing_page(landing_html([without_date]))
    assert page.tiles[0].online_since is None
    assert parse_dutch_date(page.tiles[0].online_since) is None


def test_missing_advertised_total_is_none() -> None:
    html = '<html><body><div class="product-wrapper">' + tile("7") + "</div></body></html>"
    page = parse_landing_page(html)
    assert page.advertised_total is None
    assert len(page.tiles) == 1


def test_empty_page_parses_to_zero_tiles() -> None:
    page = parse_landing_page(landing_html([], advertised=0))
    assert page.tiles == []
    assert page.advertised_total == 0


# ---------------------------------------------------------------------------
# Dutch date parsing
# ---------------------------------------------------------------------------


def test_every_dutch_month_abbreviation_parses() -> None:
    expected = {
        "jan": 1,
        "feb": 2,
        "mrt": 3,
        "apr": 4,
        "mei": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "okt": 10,
        "nov": 11,
        "dec": 12,
    }
    for abbreviation, month in expected.items():
        parsed = parse_dutch_date(f"Online sinds  15 {abbreviation}. 2026")
        assert parsed == datetime(2026, month, 15, tzinfo=UTC), abbreviation
    # Full names and the "sept" variant are tolerated too.
    assert parse_dutch_date("Online sinds 1 september 2026") == datetime(2026, 9, 1, tzinfo=UTC)
    assert parse_dutch_date("Online sinds 1 sept. 2026") == datetime(2026, 9, 1, tzinfo=UTC)
    assert parse_dutch_date("Online sinds 3 maart 2025") == datetime(2025, 3, 3, tzinfo=UTC)
    # The table covers 12 months in abbreviated and full form (plus "sept").
    assert set(DUTCH_MONTHS.values()) == set(range(1, 13))


def test_dutch_date_parser_is_total() -> None:
    for garbage in (
        None,
        "",
        "Online sinds",
        "Online sinds vandaag",
        "Online sinds gisteren",
        "Online since 15 august 2026",
        "15 foo 2026",
        "Online sinds 31 feb. 2026",  # impossible date
        "Online sinds 15 aug. 20",  # two-digit year
        "<script>alert(1)</script>",
    ):
        assert parse_dutch_date(garbage) is None, garbage


def test_single_digit_day_parses() -> None:
    assert parse_dutch_date("Online sinds  1 jul. 2026") == datetime(2026, 7, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Dedupe, budget and page failures
# ---------------------------------------------------------------------------


def test_duplicate_ids_across_landing_pages_are_dropped_once(reference_dir: Path) -> None:
    pages = [
        f"{VDAB_BASE}/vindeenjob/jobs/9000-gent",
        f"{VDAB_BASE}/vindeenjob/jobs/2000-antwerpen",
    ]
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(pages[0]).mock(
            return_value=httpx.Response(200, text=landing_html([tile("100"), tile("101")]))
        )
        respx.get(pages[1]).mock(
            return_value=httpx.Response(200, text=landing_html([tile("101"), tile("102")]))
        )
        collector = make_collector(reference_dir, landing_pages=pages)
        rows = collect(collector)
        assert len(rows) == 3
        assert len({row.source_id for row in rows}) == 3
        assert collector.tiles_seen == 4
        assert collector.duplicates_dropped == 1
        assert collector.total_elements == 3
        assert collector.completed_pages == collector.total_pages == 2


def test_page_budget_caps_the_sweep(reference_dir: Path) -> None:
    pages = [
        f"{VDAB_BASE}/vindeenjob/jobs/9000-gent",
        f"{VDAB_BASE}/vindeenjob/jobs/2000-antwerpen",
        f"{VDAB_BASE}/vindeenjob/jobs/3000-leuven",
    ]
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        for index, page in enumerate(pages):
            respx.get(page).mock(
                return_value=httpx.Response(200, text=landing_html([tile(f"{index}0")]))
            )
        collector = make_collector(reference_dir, landing_pages=pages, max_pages=2)
        rows = collect(collector)
        assert len(rows) == 2
        assert collector.total_pages == 2
        assert collector.completed_pages == 2


def test_failed_page_is_counted_and_breaks_reconciliation(reference_dir: Path) -> None:
    """A stale sitemap URL must show up as a gap, not be silently swallowed."""
    pages = [
        f"{VDAB_BASE}/vindeenjob/jobs/9000-gent",
        f"{VDAB_BASE}/vindeenjob/jobs/2000-antwerpen",
    ]
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(pages[0]).mock(return_value=httpx.Response(404, text="gone"))
        respx.get(pages[1]).mock(return_value=httpx.Response(200, text=landing_html([tile("200")])))
        collector = make_collector(reference_dir, landing_pages=pages)
        rows = collect(collector)
        assert len(rows) == 1
        assert collector.failed_pages == 1
        assert collector.completed_pages == 1
        assert collector.total_pages == 2  # expected != completed -> manifest "partial"


def test_no_pagination_parameters_are_ever_sent(reference_dir: Path) -> None:
    """?limit/?page/?start are ignored by the server and /2 404s: send none."""
    page = f"{VDAB_BASE}/vindeenjob/jobs/9000-gent"
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(page).mock(
            return_value=httpx.Response(200, text=landing_html([tile("1"), tile("2")]))
        )
        collect(make_collector(reference_dir, landing_pages=[page]))
        for call in respx.calls:
            assert call.request.url.query == b""
            assert not call.request.url.path.rstrip("/").endswith("/2")


def test_max_advertised_total_is_tracked(reference_dir: Path) -> None:
    pages = [
        f"{VDAB_BASE}/vindeenjob/jobs/9000-gent",
        f"{VDAB_BASE}/vindeenjob/jobs/2000-antwerpen",
    ]
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(pages[0]).mock(
            return_value=httpx.Response(200, text=landing_html([tile("1")], advertised=1627))
        )
        respx.get(pages[1]).mock(
            return_value=httpx.Response(200, text=landing_html([tile("2")], advertised=5360))
        )
        collector = make_collector(reference_dir, landing_pages=pages)
        collect(collector)
        assert collector.max_advertised_total == 5360


# ---------------------------------------------------------------------------
# Normalization and the region crosswalk
# ---------------------------------------------------------------------------


def test_normalized_record_matches_the_safe_fields_contract(reference_dir: Path) -> None:
    page = f"{VDAB_BASE}/vindeenjob/jobs/9000-gent"
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(page).mock(
            return_value=httpx.Response(200, text=landing_html([tile("74387619")]))
        )
        rows = collect(make_collector(reference_dir, landing_pages=[page]))

    assert len(rows) == 1
    row = rows[0]
    assert row.source == "vdab"
    assert row.country == "BE"
    assert row.lang == row.source_language == "nl"
    assert row.number_of_vacancies == 1
    assert row.scope_id == "be-flanders-all-active"
    assert row.first_published == datetime(2026, 8, 15, tzinfo=UTC)
    assert row.last_modified is None
    assert row.removed_at is None
    assert row.nuts_code == "BE234"
    assert row.nuts_label == "Arr. Gent"
    assert row.region_mapping_status == "mapped"
    assert row.region_mapping_method == "vdab_landing_postcode_nuts3"
    assert row.nuts_version == "NUTS-2024"
    assert row.occupation_mapping_status == "not_present"
    assert row.occupation_mapping_method == "not_available_vdab_html"
    assert row.esco_occupation_uri is None
    assert row.skill_mappings == []
    assert row.jobtech_taxonomy_version == ""
    assert len(row.source_id) == 64
    assert int(row.source_id, 16) >= 0  # hex digest


def test_non_flemish_postcode_is_unmapped(reference_dir: Path) -> None:
    """Brussels (410 in the Flemish register) and foreign slugs stay unmapped."""
    page = f"{VDAB_BASE}/vindeenjob/jobs/1000-brussel"
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(page).mock(return_value=httpx.Response(200, text=landing_html([tile("5")])))
        rows = collect(make_collector(reference_dir, landing_pages=[page], flemish_only=False))
    assert rows[0].region_mapping_status == "unmapped"
    assert rows[0].region_mapping_method == "not_available"
    assert rows[0].nuts_code is None


def test_crosswalk_resolution_hit_miss_and_blank(reference_dir: Path) -> None:
    crosswalk = VDABCrosswalk(reference_dir)
    hit = crosswalk.resolve("2000")
    assert (hit.nuts_code, hit.nuts_label, hit.status) == ("BE211", "Arr. Antwerpen", "mapped")
    assert crosswalk.resolve(" 3000 ").nuts_code == "BE242"
    for miss in (None, "", "1000", "9999"):
        result = crosswalk.resolve(miss)
        assert result.status == "unmapped"
        assert result.nuts_code is None
        assert result.method == "not_available"
    assert crosswalk.postcodes() == ["2000", "3000", "8000", "9000"]


def test_missing_crosswalk_file_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="reference_vdab"):
        VDABCrosswalk(tmp_path)


def test_empty_crosswalk_file_fails_loudly(tmp_path: Path) -> None:
    (tmp_path / VDAB_REFERENCE_FILE).write_text(HEADER, encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        VDABCrosswalk(tmp_path)


def test_crosswalk_reference_hashes_are_content_addressed(reference_dir: Path) -> None:
    first = crosswalk_reference_hashes(reference_dir)
    assert first.startswith(f"{VDAB_REFERENCE_FILE}:")
    assert len(first.split(":")[1]) == 64
    (reference_dir / VDAB_REFERENCE_FILE).write_text(
        HEADER + ROWS + "postcode,3500,BE221,Arr. Hasselt,https://example.invalid,2026-08-22\n",
        encoding="utf-8",
    )
    assert crosswalk_reference_hashes(reference_dir) != first


def test_short_hmac_key_is_rejected(reference_dir: Path) -> None:
    with pytest.raises(ValueError, match="hmac_key"):
        VDABCollector(
            scope_id="be-flanders-all-active",
            sweep_id="20260822T000000Z",
            observed_at=datetime(2026, 8, 22, tzinfo=UTC),
            hmac_key=b"too-short",
            reference_dir=reference_dir,
        )


def test_source_id_is_hmac_not_the_native_id(reference_dir: Path) -> None:
    page = f"{VDAB_BASE}/vindeenjob/jobs/9000-gent"
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(page).mock(
            return_value=httpx.Response(200, text=landing_html([tile("74387619")]))
        )
        rows = collect(make_collector(reference_dir, landing_pages=[page]))
    assert "74387619" not in rows[0].source_id
    # Deterministic under the same key.
    assert (
        rows[0].source_id
        == VDABCollector(
            scope_id="s",
            sweep_id="w",
            observed_at=datetime(2026, 8, 22, tzinfo=UTC),
            hmac_key=KEY,
            reference_dir=reference_dir,
        )
        .normalize({"native_id": "74387619", "first_published": None, "postcode": "9000"})
        .source_id
    )


# ---------------------------------------------------------------------------
# PII isolation
# ---------------------------------------------------------------------------


def test_pii_never_reaches_a_dumped_record(reference_dir: Path) -> None:
    page = f"{VDAB_BASE}/vindeenjob/jobs/9000-gent"
    private = tile(
        "74387619",
        employer="Bright Plus Interim BV",
        title="Verpleegkundige spoedgevallen",
        city="GENT",
        description="Bel Jan Janssens op 0470123456 of mail jan.janssens@example.invalid.",
    )
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(page).mock(return_value=httpx.Response(200, text=landing_html([private])))
        rows = collect(make_collector(reference_dir, landing_pages=[page]))

    dumped = str(rows[0].model_dump_ndjson())
    forbidden = (
        "Bright Plus",
        "Verpleegkundige",
        "GENT",
        "Jan Janssens",
        "0470123456",
        "jan.janssens@example.invalid",
        "logo.jpg",
        "vindeenjob",
        "vdab.be",
        "trefwoord",
        "9000",  # the postcode is used transiently and never persisted
        "74387619",  # the native id never leaves the worktree
        "Vaste jobs",
    )
    for token in forbidden:
        assert token not in dumped, token
    assert set(rows[0].model_dump()) <= {
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


def test_raw_record_payload_carries_no_free_text(reference_dir: Path) -> None:
    """Even the intermediate RawRecord holds only the id, the date label and postcode."""
    page = f"{VDAB_BASE}/vindeenjob/jobs/9000-gent"
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(page).mock(return_value=httpx.Response(200, text=landing_html([tile("1")])))
        collector = make_collector(reference_dir, landing_pages=[page])

        async def go() -> list[dict[str, Any]]:
            async with collector:
                return [raw.payload async for raw in collector.fetch()]

        payloads = run(go())
    assert payloads == [
        {"native_id": "1", "online_since": "Online sinds 15 aug. 2026", "postcode": "9000"}
    ]


# ---------------------------------------------------------------------------
# Retry / backoff
# ---------------------------------------------------------------------------


def test_429_is_retried_honoring_retry_after(reference_dir: Path) -> None:
    """A throttled landing page is retried after ``Retry-After``, not abandoned.

    The numeric honoring of the header lives in ``tests/test_retry.py``
    (``test_honors_retry_after_header``); this asserts the collector routes its
    landing-page fetches through that decorator.
    """
    page = f"{VDAB_BASE}/vindeenjob/jobs/9000-gent"
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, text="slow down")
        return httpx.Response(200, text=landing_html([tile("1")]))

    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(page).mock(side_effect=handler)
        rows = collect(
            make_collector(
                reference_dir,
                landing_pages=[page],
                policy=RetryPolicy(max_attempts=3, base_delay=0.0, jitter=0.0),
            )
        )

    assert calls == 2
    assert len(rows) == 1


def test_transport_error_is_retried(reference_dir: Path) -> None:
    page = f"{VDAB_BASE}/vindeenjob/jobs/9000-gent"
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(page).mock(
            side_effect=[
                httpx.ConnectTimeout("boom"),
                httpx.Response(200, text=landing_html([tile("1")])),
            ]
        )
        rows = collect(
            make_collector(
                reference_dir,
                landing_pages=[page],
                policy=RetryPolicy(max_attempts=3, base_delay=0.0, jitter=0.0),
            )
        )
    assert len(rows) == 1


def test_sitemap_server_error_propagates(reference_dir: Path) -> None:
    """Discovery failures are fatal: a partial sitemap must not look like a sweep."""
    with respx.mock:
        respx.get(VDAB_ROBOTS_URL).mock(return_value=httpx.Response(200, text=ROBOTS_TXT))
        respx.get(VDAB_KEYWORD_SITEMAP_URL).mock(return_value=httpx.Response(500, text="boom"))
        with pytest.raises(httpx.HTTPStatusError):
            collect(
                make_collector(
                    reference_dir, policy=RetryPolicy(max_attempts=1, base_delay=0.0, jitter=0.0)
                )
            )
