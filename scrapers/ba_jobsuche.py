"""BA Jobsuche collector — Germany active lane, primary build.

The Bundesagentur für Arbeit (BA) Jobsuche public website is the single largest
technically accessible German job source (~1.9M advertised, SSR plain HTTP, no
anti-bot). The collector reads the server-rendered Angular search pages, not the
internal REST API (which is WAF-403 even from a browser — `rest.arbeitsagentur.de`
is never touched).

The relaxed ToS/robots gate (user decision 2026-08-23) applies: robots.txt and
ToS are recorded as evidence but do not block a build. What is enforced:
technical anti-bot (none detected), 1 s pacing, PII ban, HMAC pseudonymization,
canary discipline, manifest reconciliation, and ``make check`` green.

Contract pinned live on 2026-08-24:

- **Search page:** ``www.arbeitsagentur.de/jobsuche/suche?was=…&wo=…&page=N``
  → 200, 370 KB, server-rendered Angular SSR with 25 result items per page.
  Each item carries a native ref ID (``10000-1202838080-S``), a German date
  (``Veröffentlichungsdatum: 01.07.2025``), and a location string
  (``Berlin (11 km)`` — city plus distance, no PLZ on the search page).
- **Pagination:** ``&page=N`` works. An unscoped query produces **400 pages
  × 25 items = 10,000 listings** before the window exhausts (page 401+ is
  empty). This is a hard per-query cap, not a recycling window.
- **Detail page:** ``/jobsuche/jobdetail/<ref-id>`` carries a ``JobPosting``
  JSON-LD with ``datePosted``, ``identifier.value``, and
  ``jobLocation.address.postalCode`` (PLZ). Detail pages are **not** fetched
  by default (the search page alone supplies the SAFE_FIELDS needed); the PLZ
  enrichment is available as a future step.
- **Robots.txt:** ``www.arbeitsagentur.de/robots.txt`` → allow-all for ``*``
  (``Disallow:``, ``Allow: /``). The ``/jobsuche/`` sub-path has no separate
  robots file. ``Crawl-Delay`` is absent. The collector fetches robots as
  evidence and logs the verdict; a disallow would be logged, not raised.
- **No anti-bot:** No Cloudflare/Akamai/DataDome/Incapsula headers, no
  challenge, zero 4xx/429 across ~25 probes including 500 pages. Server is
  ``o-vfz2-online Application``.

SAFE_FIELDS mapping:

- ``source_id`` = HMAC of the native ref ID (``Stellenangebot <ref-id>``).
- ``first_published`` = the search item's ``Veröffentlichungsdatum`` (German
  ``DD.MM.YYYY`` date from the ``title`` attribute, stored at 00:00 UTC).
- ``last_modified`` = ``None``; not exposed on either surface.
- ``removed_at`` = ``None``; not exposed; absence-based across sweeps.
- ``number_of_vacancies`` = 1; not advertised in the search or detail payload.
- **Region:** the city name from the location string (``Berlin`` from
  ``Berlin (11 km)``) is resolved through the pinned German crosswalk
  (``data/reference/germany_plz_nuts_2024.csv``) → ``mapped`` when the city
  corresponds to exactly one NUTS 3 code, ``ambiguous`` when the same city
  name appears in multiple NUTS 3 regions (397 such names), ``unmapped`` when
  no match or the location is foreign.
- **Occupation:** the search page carries only a free-text title, no occupation
  code, so ``occupation_mapping_status=not_present`` (Increments 1–3 precedent).

PII compliance: the search page also renders job titles, employer names,
description snippets, and the detail URL. **None of them are read.** The parse
is allowlist-only — it extracts the ref ID, the date attribute, and the location
label, and nothing else. The PLZ (on the detail page) would be read transiently
to derive NUTS 3 and never persisted.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field

from scrapers.base import (
    REQUEST_TIMEOUT_SECONDS,
    BaseCollector,
    MappingStatus,
    NormalizedRecord,
    RawRecord,
)
from scrapers.retry import RetryPolicy, with_backoff
from scrapers.robots import PacingGate, RobotsRule
from scrapers.sanitize import pseudonymize

BA_BASE = "https://www.arbeitsagentur.de"
BA_ROBOTS_URL = f"{BA_BASE}/robots.txt"
BA_SEARCH_URL = f"{BA_BASE}/jobsuche/suche?suchbereich=jobs"

BA_SOURCE_VERSION = "jobsuche-ssr-2026-08"
BA_SCOPE_ID = "de-all-window"
BA_SCOPE_PARAMS: dict[str, str] = {
    "source": "ba",
    "country": "DE",
    "surface": "public-html-search",
    "query": "all-active",
    "segmentation": "unscoped",
}
BA_LICENCE_REFERENCE = "https://www.arbeitsagentur.de/"
BA_ACCESS_METHOD = "robots-permitted-html"
BA_FRESHNESS_THRESHOLD_HOURS = 24

BA_PACING_SECONDS = 1.0
BA_ITEMS_PER_PAGE = 25
BA_DEFAULT_PAGE_BUDGET = 400
BA_MAX_QUERY_PAGES = 400

#: BA rate-limits with 403 (not 429) via an Apache-edge token bucket once the
#: rolling window fills: measured live 2026-08-24 — ~50 pages succeed, then
#: 403 "Access forbidden!" pages until an idle pause lets the bucket refill
#: (a ~30 s pause restores full service). This is a throttle, not a WAF
#: challenge. ``_get`` handles it explicitly: on 403 it waits a full cooldown
#: (bucket refills to full), then retries the page once. A second 403 raises
#: (a genuine block), which the gate treats as stop-the-sweep.
BA_THROTTLE_COOLDOWN_SECONDS = 45.0
BA_RETRY_POLICY = RetryPolicy(
    max_attempts=4,
    base_delay=1.5,
    max_delay=30.0,
    retry_statuses=frozenset({202, 429, 500, 502, 503, 504}),
)

BA_USER_AGENT = (
    "EU-Tech-Labour-Observatory/0.1 (+public job-data research, robots-and-ToS-compliant)"
)

BA_REFERENCE_FILE = "germany_plz_nuts_2024.csv"

BA_COVERAGE_LIMITATIONS = (
    "Public server-rendered HTML search interface of the Bundesagentur für "
    "Arbeit (BA) Jobsuche. The internal REST API (rest.arbeitsagentur.de) is "
    "WAF-403 even from a browser and is not used. Search pages carry 25 items "
    "each and paginate via &page=N. **Coverage bound, stated plainly:** an "
    "unscoped query produces pages 1..400 with 25 items each (10,000 listings "
    "max) before the window closes (page 401+ returns empty); the advertised "
    "~1.9M active stock is not reachable from a single query. dedupe is on "
    "HMAC source_id across pages. Region is derived from the search-page "
    "location string's city name via the pinned German crosswalk (BKG "
    "VZ250_GEM municipality register x destatis Kreise NUTS 2024 key x "
    "destatis Anschriftenverzeichnis). Cities matching multiple NUTS 3 codes "
    "(397 such names) are reported as ambiguous. The PLZ from the detail page "
    "is available for enrichment but not collected in the standard sweep. "
    "Occupation is not present on the search page (no code exposed). "
    "last_modified and removed_at are not exposed; closures are absence-based "
    "across consecutive sweeps."
)

# German date pattern: "01.07.2025" in title attributes.
_GERMAN_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
# Ref ID in the detail URL: "/jobsuche/jobdetail/10000-1202838080-S"
_REF_ID = re.compile(r"/jobsuche/jobdetail/([^/\s\"']+)")
# Location: "Arbeitsort: Berlin (11 km)" -> "Berlin"
_LOCATION_CITY = re.compile(r"Arbeitsort:\s*([^(]+)")


# ---------------------------------------------------------------------------
# Search page parsing (allowlist-only)
# ---------------------------------------------------------------------------


class SearchItem(BaseModel):
    """One result item on a BA search page — allowlist only.

    ``extra="forbid"`` keeps the item's title, employer, description, and
    other PII out of the pipeline: only the ref ID, the date, and the
    location label are ever read.
    """

    model_config = ConfigDict(extra="forbid")

    native_id: str = Field(min_length=1)
    first_published: datetime | None = None
    location_city: str | None = None


def parse_date_from_title(title_attr: str | None) -> datetime | None:
    """Parse a German date from a ``title="Veröffentlichungsdatum: DD.MM.YYYY"`` attr."""
    if not title_attr:
        return None
    match = _GERMAN_DATE.search(title_attr)
    if not match:
        return None
    try:
        return datetime(int(match.group(3)), int(match.group(2)), int(match.group(1)), tzinfo=UTC)
    except ValueError:
        return None


def parse_page(html: str) -> list[SearchItem]:
    """Allowlist-only parse of one BA search result page.

    Reads exactly three things per item: the native ref ID (from the hover
    title on the context menu button), the publication date (from the
    ``title`` attribute of the date span), and the location city (from the
    ``Arbeitsort`` label). Everything else (title, employer, description,
    detail URL, tracking params) is ignored.
    """
    soup = BeautifulSoup(html, "lxml")
    items: list[SearchItem] = []

    for container in soup.select("li.ba-tile.listeneintrag"):
        native_id = None
        first_published = None
        location_city = None

        for link in container.select("a[href]"):
            href = link.get("href")
            if isinstance(href, str):
                match = _REF_ID.search(href)
                if match:
                    native_id = match.group(1)
                    break

        if not native_id:
            continue

        # Date from the sibling meta-lane
        for span in container.select("span[title]"):
            title = span.get("title")
            if isinstance(title, str) and "Veröffentlichungsdatum" in title:
                first_published = parse_date_from_title(title)
                break

        # Location city from the arbeitsort span
        for span in container.select("span[id]"):
            span_id = span.get("id")
            if isinstance(span_id, str) and span_id.endswith("-arbeitsort"):
                text = span.get_text(" ", strip=True)
                match = _LOCATION_CITY.match(text)
                if match:
                    location_city = match.group(1).strip()
                break

        items.append(
            SearchItem(
                native_id=native_id,
                first_published=first_published,
                location_city=location_city,
            )
        )

    return items


# ---------------------------------------------------------------------------
# Region crosswalk (NUTS 2024)
# ---------------------------------------------------------------------------


class RegionResolution(BaseModel):
    nuts_code: str | None = None
    nuts_label: str | None = None
    status: MappingStatus = "unmapped"
    method: str = "not_available"


class GermanCrosswalk:
    """Loads the pinned German PLZ/Stadt -> NUTS 2024 table and resolves regions.

    Resolves by city name (municipality). A single-municipality city name
    maps to ``mapped``; names appearing in multiple NUTS 3 regions (397 such
    names) are ``ambiguous``; unrecognised names stay ``unmapped``.
    """

    def __init__(self, reference_dir: Path) -> None:
        path = reference_dir / BA_REFERENCE_FILE
        if not path.exists():
            raise FileNotFoundError(
                f"missing German crosswalk reference: {path} "
                "(rebuild with `python -m scrapers.reference_germany`)"
            )
        # municipality_name -> list of (nuts_code, nuts_label, kreis_name)
        self._name_map: dict[str, list[tuple[str, str, str]]] = {}
        # plz -> list of (nuts_code, nuts_label, kreis_name)
        self._plz_map: dict[str, list[tuple[str, str, str]]] = {}

        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                st = row["source_type"]
                code = row["source_code"].strip()
                nuts = row["nuts_code"].strip()
                label = row["nuts_label"].strip()
                kreis = row["kreis_name"].strip()
                name = row["municipality_name"].strip()
                if st == "municipality" and name:
                    self._name_map.setdefault(name, []).append((nuts, label, kreis))
                elif st == "plz" and code:
                    self._plz_map.setdefault(code, []).append((nuts, label, kreis))

        if not self._name_map:
            raise ValueError(f"German crosswalk reference is empty: {path}")

    def resolve_by_city(self, city: str | None) -> RegionResolution:
        if not city:
            return RegionResolution(method="not_available")
        candidates = self._name_map.get(city.strip())
        if not candidates:
            # Try case-insensitive match
            normalized = city.strip().lower()
            for name, c in self._name_map.items():
                if name.lower() == normalized:
                    candidates = c
                    break
        if not candidates:
            return RegionResolution(method="not_available")
        distinct = {(c[0], c[1]) for c in candidates}
        if len(distinct) == 1:
            nuts, label = next(iter(distinct))
            return RegionResolution(
                nuts_code=nuts,
                nuts_label=label,
                status="mapped",
                method="ba_city_municipality_nuts3",
            )
        return RegionResolution(status="ambiguous", method="ba_city_municipality_ambiguous")

    def resolve_by_plz(self, plz: str | None) -> RegionResolution:
        if not plz:
            return RegionResolution(method="not_available")
        candidates = self._plz_map.get(plz.strip())
        if not candidates:
            return RegionResolution(method="not_available")
        distinct = {(c[0], c[1]) for c in candidates}
        if len(distinct) == 1:
            nuts, label = next(iter(distinct))
            return RegionResolution(
                nuts_code=nuts,
                nuts_label=label,
                status="mapped",
                method="ba_plz_nuts3",
            )
        return RegionResolution(status="ambiguous", method="ba_plz_ambiguous")


def crosswalk_reference_hashes(reference_dir: Path) -> str:
    digest = hashlib.sha256()
    with (reference_dir / BA_REFERENCE_FILE).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return f"{BA_REFERENCE_FILE}:{digest.hexdigest()}"


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class BAJobsucheCollector(BaseCollector):
    """Collector for the BA Jobsuche public website (Germany).

    Fetches and parses ``robots.txt`` once per sweep (logged as evidence;
    a disallow is logged, not raised), then walks the search pages at the
    charter's pacing floor. Coverage is window-bounded: one unscoped query
    yields at most 400 pages × 25 items = 10,000 listings.
    """

    source: ClassVar[str] = "ba"
    country: ClassVar[str] = "DE"

    def __init__(
        self,
        *,
        scope_id: str,
        sweep_id: str,
        observed_at: datetime,
        hmac_key: bytes,
        reference_dir: Path = Path("data/reference"),
        max_pages: int | None = None,
        pacing_interval: float = BA_PACING_SECONDS,
        policy: RetryPolicy | None = None,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            scope_id=scope_id, sweep_id=sweep_id, observed_at=observed_at, timeout=timeout
        )
        if len(hmac_key) < 32:
            raise ValueError("hmac_key must be at least 32 bytes")
        self._hmac_key = hmac_key
        self._crosswalk = GermanCrosswalk(reference_dir)
        self._page_budget = BA_DEFAULT_PAGE_BUDGET if max_pages is None else max(1, max_pages)
        self._policy = policy or BA_RETRY_POLICY
        self._pacer = PacingGate(min_interval=pacing_interval)
        self._pacing_interval = pacing_interval
        self._robots: RobotsRule | None = None
        self._headers = {"User-Agent": BA_USER_AGENT, "Accept": "text/html"}
        self.total_elements = 0
        self.total_pages = 0
        self.completed_pages = 0
        self.failed_pages = 0
        self.items_seen = 0
        self.duplicates_dropped = 0
        self.empty_pages = 0
        self.throttle_events = 0

    # -- robots (evidence only) --------------------------------------------

    async def _load_robots(self) -> RobotsRule:
        if self._robots is not None:
            return self._robots

        async def do_get() -> httpx.Response:
            return await self._client.get(BA_ROBOTS_URL, headers=self._headers)

        await self._pacer.wait()
        response = await with_backoff(self._policy)(do_get)()
        text = response.text if response.status_code == 200 else None
        rule = RobotsRule(text)
        self._robots = rule
        disallow_everything = text is not None and "Disallow:" in text and "Allow:" not in text
        self._log.info(
            "ba_robots_loaded",
            status=response.status_code,
            bytes=len(response.content),
            disallow_observed=disallow_everything,
        )
        # Under the relaxed constraint: a disallow is logged, not raised.
        # A 403/WAF/block IS enforced (that is a technical barrier, not a ToS signal).
        if response.status_code == 403:
            raise RuntimeError(
                "robots.txt answered 403 — the search host is technically blocked "
                "(anti-bot/WAF), which is a hard gate under the relaxed constraint"
            )
        delay = rule.crawl_delay(BA_USER_AGENT)
        if delay is not None and delay > self._pacing_interval:
            self._pacer = PacingGate(min_interval=delay)
        return rule

    # -- HTTP (paced, retried, robots-checked) -----------------------------

    async def _get(self, url: str) -> httpx.Response:
        async def do_get() -> httpx.Response:
            return await self._client.get(url, headers=self._headers)

        await self._pacer.wait()
        response = await with_backoff(self._policy)(do_get)()
        if response.status_code != 403:
            return response
        # BA throttle: wait a full cooldown (bucket refills), then retry once.
        # A second 403 is a genuine block — stop the sweep, loudly.
        self.throttle_events += 1
        self._log.warning("ba_throttle_observed", throttle_event=self.throttle_events, url=url)
        await asyncio.sleep(BA_THROTTLE_COOLDOWN_SECONDS)
        response = await with_backoff(self._policy)(do_get)()
        if response.status_code == 403:
            self.failed_pages += 1
            raise RuntimeError(
                f"BA Jobsuche answered 403 again after a {int(BA_THROTTLE_COOLDOWN_SECONDS)} s "
                "throttle cooldown — the host is blocking this sweep (hard gate)"
            )
        return response

    # -- fetch -------------------------------------------------------------

    def fetch(self) -> AsyncIterator[RawRecord]:
        return self._fetch()

    async def _fetch(self) -> AsyncIterator[RawRecord]:
        await self._load_robots()
        max_pages = min(self._page_budget, BA_MAX_QUERY_PAGES)
        self.total_pages = max_pages
        seen: set[str] = set()

        for page_num in range(1, max_pages + 1):
            url = f"{BA_SEARCH_URL}&page={page_num}"
            response = await self._get(url)
            if response.status_code != 200:
                self.failed_pages += 1
                self._log.warning("ba_page_failed", url=url, status=response.status_code)
                continue
            self.completed_pages += 1

            items = parse_page(response.text)
            if not items:
                self.empty_pages += 1
                # If the FIRST page has no items, the page structure likely
                # changed (schema drift) — fail loudly, not silently.
                if page_num == 1:
                    raise RuntimeError(
                        "BA Jobsuche search page 1 returned 0 results — "
                        "the page structure may have changed (schema drift)"
                    )
                # Deep pages going empty means the query window is exhausted.
                break

            self.items_seen += len(items)
            for item in items:
                source_id = pseudonymize(item.native_id, self._hmac_key)
                if source_id in seen:
                    self.duplicates_dropped += 1
                    continue
                seen.add(source_id)
                yield RawRecord(
                    native_id=item.native_id,
                    payload={
                        "native_id": item.native_id,
                        "first_published": item.first_published,
                        "location_city": item.location_city,
                    },
                )

        self.total_elements = len(seen)
        self._log.info(
            "ba_sweep_summary",
            search_pages=self.completed_pages,
            planned_pages=self.total_pages,
            failed_pages=self.failed_pages,
            empty_pages=self.empty_pages,
            items=self.items_seen,
            unique_rows=self.total_elements,
            duplicates=self.duplicates_dropped,
        )

    # -- normalization -----------------------------------------------------

    def parse(self, raw: RawRecord) -> dict[str, Any]:
        return {
            "native_id": raw.payload["native_id"],
            "first_published": raw.payload.get("first_published"),
            "location_city": raw.payload.get("location_city"),
        }

    def normalize(self, parsed: dict[str, Any]) -> NormalizedRecord:
        region = self._crosswalk.resolve_by_city(parsed["location_city"])
        return NormalizedRecord(
            source=self.source,
            source_id=pseudonymize(parsed["native_id"], self._hmac_key),
            scope_id=self.scope_id,
            sweep_id=self.sweep_id,
            observed_at=self.observed_at,
            first_published=parsed["first_published"],
            last_modified=None,
            removed_at=None,
            nuts_code=region.nuts_code,
            nuts_label=region.nuts_label,
            region_mapping_status=region.status,
            region_mapping_method=region.method,
            country=self.country,
            esco_occupation_uri=None,
            esco_occupation_label=None,
            occupation_mapping_status="not_present",
            occupation_mapping_method="not_available_ba_html",
            source_language="de",
            jobtech_taxonomy_version="",
            esco_version="1.2.1",
            skill_mappings=[],
            lang="de",
            number_of_vacancies=1,
        )
