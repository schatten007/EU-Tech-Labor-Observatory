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
import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field

from scrapers.ba_panel import (
    BA_PANEL_PAGE_CAP,
    BA_PANEL_UMKREIS,
    PanelEntry,
)
from scrapers.ba_segments import BA_BUNDESLAENDER, BA_LEVEL4_RECENCY_DAYS, Segment, SegmentFrontier
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
#: Increment 9 scope: per-segment regional census (see SCRAPER_FEASIBILITY.md
#: "BA Jobsuche — segmented stock"). The scope_hash distinguishes partitions
#: from the two strategies; the main app must not be fed both DE scopes at once
#: (`scripts/publish.py:756` `_verify_single_scope` raises on a second scope).
BA_SEGMENTED_SCOPE_ID = "de-stock-segmented"
BA_SEGMENTED_SCOPE_PARAMS: dict[str, str] = {
    "source": "ba",
    "country": "DE",
    "surface": "public-html-search",
    "query": "segmented-regional-census",
    "segmentation": "segment-provenance",
    "region_inference": "three-tier",
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
# SSR state blob carrying the search envelope (probe E1, 2026-09-01).
_NG_STATE = re.compile(
    r"<script[^>]*id=[\"']ng-state[\"'][^>]*>(.*?)</script>",
    re.DOTALL | re.IGNORECASE,
)


def parse_search_envelope(html: str) -> tuple[int | None, str | None, str | None]:
    """Read ``(total_hits, resolved_place, search_mode)`` from the SSR state.

    The visible HTML carries no ``Treffer``/``Ergebnisse`` node, but the
    ``<script id="ng-state">`` blob does: ``suchergebnis.maxErgebnisse`` is the
    exact number of hits the source advertises for the query, and
    ``suchergebnis.woOutput`` echoes the location it actually resolved
    (``bereinigterOrt``) and the mode it used (``suchmodus`` is one of
    ``ORTSUCHE``, ``UMKREISSUCHE``, ``UNGUELTIG``). Allowlist-only: nothing else
    is read out of the state, and none of it is a personal datum.
    """
    match = _NG_STATE.search(html)
    if match is None:
        return (None, None, None)
    try:
        state = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return (None, None, None)
    if not isinstance(state, dict):
        return (None, None, None)
    for value in state.values():
        if not isinstance(value, dict) or "maxErgebnisse" not in value:
            continue
        total = value.get("maxErgebnisse")
        wo_output = value.get("woOutput")
        place: str | None = None
        mode: str | None = None
        if isinstance(wo_output, dict):
            raw_place = wo_output.get("bereinigterOrt")
            raw_mode = wo_output.get("suchmodus")
            place = str(raw_place) if raw_place else None
            mode = str(raw_mode) if raw_mode else None
        return (int(total) if isinstance(total, (int, float)) else None, place, mode)
    return (None, None, None)


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


#: Non-geographic location markers BA states on the search page. These are not
#: lookup failures: the source stated a location it cannot narrow to one NUTS 3,
#: so they resolve to ``ambiguous`` with a distinct method, never to ``unmapped``
#: (which keeps ``unmapped`` meaning "our lookup failed" — the honest signal
#: that drives mapper work). Lowercased marker -> (status, method).
BA_NON_GEOGRAPHIC_MARKERS: dict[str, tuple[MappingStatus, str]] = {
    "verschiedene arbeitsorte": ("ambiguous", "ba_location_multiple"),
    "deutschland": ("ambiguous", "ba_location_nationwide"),
    "bundesweit": ("ambiguous", "ba_location_nationwide"),
    "ausland": ("ambiguous", "ba_location_foreign"),
}

#: Comma-qualifier -> NUTS-1 prefix alias map (the German Bundesland is
#: ``nuts_code[:3]``: DE1=BW … DEG=TH). BA disambiguates same-named places with
#: a qualifier (``Heidelberg, Neckar``, ``Neunkirchen, Saar``,
#: ``Rosenheim, Oberbayern``); filtering the city's NUTS-3 candidates by the
#: qualifier's NUTS-1 prefix resolves them without rebuilding the crosswalk.
BA_NUTS1_ALIASES: dict[str, str] = {
    "baden": "DE1",
    "württemberg": "DE1",
    "neckar": "DE1",
    "hegau": "DE1",
    "oberbayern": "DE2",
    "niederbayern": "DE2",
    "oberpfalz": "DE2",
    "oberfranken": "DE2",
    "mittelfranken": "DE2",
    "unterfranken": "DE2",
    "schwaben": "DE2",
    "bayern": "DE2",
    "rheinland": "DEA",
    "westfalen": "DEA",
    "nordrhein-westfalen": "DEA",
    "pfalz": "DEB",
    "eifel": "DEB",
    "rheinland-pfalz": "DEB",
    "hessen": "DE7",
    "saar": "DEC",
    "saarland": "DEC",
    "sachsen": "DED",
    "anhalt": "DEE",
    "sachsen-anhalt": "DEE",
    "holstein": "DEF",
    "schleswig": "DEF",
    "schleswig-holstein": "DEF",
    "thüringen": "DEG",
    "mecklenburg": "DE8",
    "mecklenburg-vorpommern": "DE8",
    "pommern": "DE8",
    "brandenburg": "DE4",
    "niedersachsen": "DE9",
    "berlin": "DE3",
    "hamburg": "DE6",
    "bremen": "DE5",
}


def normalize_location(
    crosswalk: GermanCrosswalk,
    city: str | None,
    *,
    segment_nuts1: str | None = None,
    segment_nuts3: str | None = None,
) -> RegionResolution:
    """Shared three-tier-aware location normalizer (plan §5).

    Tier 1: the city resolves to exactly one NUTS 3 -> ``mapped``. A comma
    qualifier is first stripped, and when it names a known NUTS-1 region the
    candidates are filtered by that prefix. Tier 2: an ambiguous city is
    narrowed by the current segment's NUTS-1/NUTS-3 context -> ``mapped`` /
    ``ba_segment_disambiguated``. Non-geographic markers map to ``ambiguous``.
    Tier 3 (segment provenance) is applied by the collector's ``normalize``,
    not here, because it needs the segment's ``umkreis`` policy.
    """
    if not city:
        return RegionResolution(method="not_available")
    text = city.strip()
    lower = text.lower()
    for marker, (status, method) in BA_NON_GEOGRAPHIC_MARKERS.items():
        if lower == marker or lower.startswith(f"{marker} "):
            return RegionResolution(status=status, method=method)

    base = text
    qualifier: str | None = None
    if "," in text:
        parts = [part.strip() for part in text.split(",", 1)]
        base, qualifier = parts[0], parts[1]

    candidates = crosswalk.candidates_for_name(base)
    qualifier_prefix = BA_NUTS1_ALIASES.get(qualifier.lower()) if qualifier else None
    if qualifier_prefix and candidates:
        filtered = [c for c in candidates if c[0].startswith(qualifier_prefix)]
        if filtered:
            distinct = {(c[0], c[1]) for c in filtered}
            if len(distinct) == 1:
                nuts, label = next(iter(distinct))
                return RegionResolution(
                    nuts_code=nuts,
                    nuts_label=label,
                    status="mapped",
                    method="ba_city_qualifier_nuts3",
                )
            candidates = filtered

    if candidates:
        distinct = {(c[0], c[1]) for c in candidates}
        if len(distinct) == 1:
            nuts, label = next(iter(distinct))
            return RegionResolution(
                nuts_code=nuts,
                nuts_label=label,
                status="mapped",
                method="ba_city_municipality_nuts3",
            )
        # Tier 2: the segment's own region narrows an ambiguous city.
        narrowed: list[tuple[str, str, str]] = []
        if segment_nuts3:
            narrowed = [c for c in candidates if c[0] == segment_nuts3]
        if not narrowed and segment_nuts1:
            narrowed = [c for c in candidates if c[0].startswith(segment_nuts1)]
        if len({(c[0], c[1]) for c in narrowed}) == 1:
            nuts, label, _kreis = next(iter(narrowed))
            return RegionResolution(
                nuts_code=nuts,
                nuts_label=label,
                status="mapped",
                method="ba_segment_disambiguated",
            )
        return RegionResolution(status="ambiguous", method="ba_city_municipality_ambiguous")

    return RegionResolution(method="not_available")


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
        # municipality_name -> list of (plz, (nuts_code, nuts_label, kreis_name))
        # built from PLZ rows only, used to disambiguate multi-NUTS-3 names.
        self._plz_name_map: dict[str, list[tuple[str, tuple[str, str, str]]]] = {}

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
                    if name:
                        self._plz_name_map.setdefault(name, []).append((code, (nuts, label, kreis)))

        if not self._name_map:
            raise ValueError(f"German crosswalk reference is empty: {path}")

    # -- shared accessors (segment building + normalizer) -------------------

    def candidates_for_name(self, name: str) -> list[tuple[str, str, str]]:
        """All ``(nuts_code, nuts_label, kreis_name)`` candidates for a city name."""
        name = name.strip()
        candidates = self._name_map.get(name)
        if not candidates:
            normalized = name.lower()
            for known, c in self._name_map.items():
                if known.lower() == normalized:
                    candidates = c
                    break
        return list(candidates or ())

    def municipality_names_by_nuts3(self) -> dict[str, set[str]]:
        """Distinct municipality names -> set of NUTS-3 codes they appear in."""
        out: dict[str, set[str]] = {}
        for name, candidates in self._name_map.items():
            out[name] = {c[0] for c in candidates}
        return out

    def plz_rows_for_name(self, name: str) -> list[tuple[str, str]]:
        """PLZ rows belonging to a municipality name: ``(plz, nuts_code)`` pairs."""
        name = name.strip()
        return [(plz, nuts) for plz, (nuts, _label, _kreis) in self._plz_name_map.get(name, [])]

    def plz_codes_for_nuts(self, nuts_code: str) -> list[str]:
        """PLZ codes whose NUTS 3 matches, for subdividing a truncated segment."""
        return [
            plz
            for plz, candidates in self._plz_map.items()
            if any(c[0] == nuts_code for c in candidates)
        ]

    def label_for_nuts(self, nuts_code: str) -> str | None:
        """Reference label for a NUTS-3 code, or ``None`` when the code is unknown.

        Tier-3 provenance resolves a code the page's city string could not; this
        supplies the matching label so the resolution is complete, matching
        every Tier-1/2 path.
        """
        for candidates in self._name_map.values():
            for nuts, label, _kreis in candidates:
                if nuts == nuts_code:
                    return label
        for candidates in self._plz_map.values():
            for nuts, label, _kreis in candidates:
                if nuts == nuts_code:
                    return label
        return None

    def resolve_by_city(self, city: str | None) -> RegionResolution:
        return normalize_location(self, city)

    def resolve_by_city_segmented(
        self,
        city: str | None,
        *,
        segment_nuts1: str | None = None,
        segment_nuts3: str | None = None,
    ) -> RegionResolution:
        return normalize_location(
            self, city, segment_nuts1=segment_nuts1, segment_nuts3=segment_nuts3
        )

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
        # Segmented mode (Increment 9). When ``frontier`` is given, the sweep
        # walks that frontier's pending segments instead of the single unscoped
        # query; ``max_pages`` is then ignored (segments are atomic).
        frontier: SegmentFrontier | None = None,
        frontier_path: Path = Path("data/state/ba_segment_frontier.json"),
        max_segments: int | None = None,
        min_level: int = 0,
        umkreis: int = 0,
        # Frozen NUTS-3 panel mode (Increment 9, step 2b). When ``panel`` is
        # given, the sweep walks exactly that pinned query list, page-capped;
        # ``frontier`` and ``max_pages`` are then irrelevant. No subdivision, no
        # adaptivity: the query set must stay byte-identical across sweeps.
        panel: list[PanelEntry] | None = None,
        panel_page_cap: int = BA_PANEL_PAGE_CAP,
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
        # Segmented-mode counters (populated only when a frontier is given).
        self._frontier = frontier
        self._frontier_path = frontier_path
        self._max_segments = max_segments
        self._min_level = min_level
        self._umkreis = umkreis
        self.segments_processed = 0
        self.segments_complete = 0
        self.segments_truncated = 0
        self.segments_subdivided = 0
        self.segments_failed = 0
        self.active_segment: Segment | None = None
        # Panel-mode state (populated only when a panel is given).
        self._panel = panel
        self._panel_page_cap = max(1, panel_page_cap)
        self.panel_regions_queried = 0
        self.panel_regions_with_rows = 0
        self.panel_regions_empty = 0
        self.panel_regions_capped = 0
        self.panel_regions_short = 0
        self.panel_locality_mismatches = 0
        self.panel_missing_envelope = 0
        #: nuts_code -> {advertised, rows, pages, form, query, place, mode}
        self.panel_regions: dict[str, dict[str, Any]] = {}

    @property
    def frontier(self) -> SegmentFrontier | None:
        return self._frontier

    @property
    def measured_stock_lower_bound(self) -> int:
        """Sum of rows over complete segments — the measured active-stock lower bound."""
        if self._frontier is None:
            return 0
        return sum(
            s.rows_yielded for s in self._frontier.segments.values() if s.status == "complete"
        )

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
        if self._panel is not None:
            return self._fetch_panel()
        if self._frontier is not None:
            return self._fetch_segmented()
        return self._fetch()

    def _segment_url(self, key: str, page_num: int) -> str:
        """Build the full BA search URL for a segment key at a given page."""
        if key:
            return f"{BA_SEARCH_URL}&{key}&page={page_num}"
        return f"{BA_SEARCH_URL}&page={page_num}"

    @staticmethod
    def _panel_locality_ok(entry: PanelEntry, place: str | None, mode: str | None) -> bool:
        """Assert the source resolved the queried place, using its own echo.

        ``woOutput.bereinigterOrt`` is BA's cleaned rendering of the location it
        searched ("Hof" -> "Hof, Saale"; "72213" -> "72213"), and ``suchmodus``
        is ``UNGUELTIG`` when the string did not resolve at all. Comparing the
        first comma component catches the fuzzy misses seen in probe E3
        ("Osterholz" -> "Osterholz bei Bopfingen").
        """
        if mode == "UNGUELTIG" or not place:
            return False
        resolved = place.split(",")[0].strip().casefold()
        return resolved == entry.value.strip().casefold()

    async def _fetch_panel(self) -> AsyncIterator[RawRecord]:
        """Walk the frozen NUTS-3 panel: one pinned query per region, page-capped.

        No frontier, no subdivision, no adaptivity — the query list is the pinned
        panel and nothing observed during the sweep may change it, because a
        query set that drifts between sweeps fabricates closures and corrupts
        survival durations. The per-region page plan comes from the source's own
        advertised total (``maxErgebnisse``) clamped by the declared cap, so
        ``expected_pages`` describes the declared capped scope.
        """
        assert self._panel is not None
        await self._load_robots()
        seen: set[str] = set()
        self.total_pages = 0
        self.completed_pages = 0

        for entry in self._panel:
            self.panel_regions_queried += 1
            advertised: int | None = None
            place: str | None = None
            mode: str | None = None
            region_rows = 0
            pages_done = 0
            planned = 1
            # Page 1 is always planned: it is what reveals the region's total.
            self.total_pages += 1
            page_num = 1
            while page_num <= planned:
                url = self._segment_url(entry.query, page_num)
                response = await self._get(url)
                if response.status_code != 200:
                    self.failed_pages += 1
                    self._log.warning(
                        "ba_panel_page_failed",
                        nuts_code=entry.nuts_code,
                        page=page_num,
                        status=response.status_code,
                    )
                    break
                self.completed_pages += 1
                pages_done += 1

                if page_num == 1:
                    advertised, place, mode = parse_search_envelope(response.text)
                    if advertised is None:
                        # The envelope is the panel's denominator; losing it is
                        # schema drift, so it is counted, not silently ignored.
                        self.panel_missing_envelope += 1
                    else:
                        pages_available = (advertised + BA_ITEMS_PER_PAGE - 1) // BA_ITEMS_PER_PAGE
                        planned = max(1, min(self._panel_page_cap, pages_available))
                        if pages_available > self._panel_page_cap:
                            self.panel_regions_capped += 1
                        # Pages 2..planned join the declared plan.
                        self.total_pages += planned - 1
                    if not self._panel_locality_ok(entry, place, mode):
                        self.panel_locality_mismatches += 1
                        self._log.warning(
                            "ba_panel_locality_mismatch",
                            nuts_code=entry.nuts_code,
                            queried=entry.value,
                            resolved=place,
                            mode=mode,
                        )

                items = parse_page(response.text)
                if not items:
                    self.empty_pages += 1
                    break

                self.items_seen += len(items)
                for item in items:
                    source_id = pseudonymize(item.native_id, self._hmac_key)
                    if source_id in seen:
                        self.duplicates_dropped += 1
                        continue
                    seen.add(source_id)
                    region_rows += 1
                    yield RawRecord(
                        native_id=item.native_id,
                        payload={
                            "native_id": item.native_id,
                            "first_published": item.first_published,
                            "location_city": item.location_city,
                            "segment_key": entry.query,
                            "segment_nuts3": entry.nuts_code,
                            "segment_nuts1": entry.nuts1,
                            "segment_level": 2,
                            "umkreis": BA_PANEL_UMKREIS,
                        },
                    )

                if len(items) < BA_ITEMS_PER_PAGE:
                    # Pagination closed before the plan: the advertised total was
                    # stale. Drop the un-walked remainder from the plan (so the
                    # manifest identity describes what the declared rule actually
                    # required) and record the discrepancy.
                    break
                page_num += 1

            if pages_done and pages_done < planned:
                self.panel_regions_short += 1
                self.total_pages -= planned - pages_done

            if region_rows:
                self.panel_regions_with_rows += 1
            else:
                self.panel_regions_empty += 1

            self.panel_regions[entry.nuts_code] = {
                "form": entry.form,
                "query": entry.query,
                "advertised": advertised,
                "rows": region_rows,
                "pages": pages_done,
                "planned_pages": planned,
                "resolved_place": place,
                "search_mode": mode,
            }

        self.total_elements = len(seen)
        self._log.info(
            "ba_panel_sweep_summary",
            regions=self.panel_regions_queried,
            regions_with_rows=self.panel_regions_with_rows,
            regions_empty=self.panel_regions_empty,
            regions_capped=self.panel_regions_capped,
            regions_short=self.panel_regions_short,
            locality_mismatches=self.panel_locality_mismatches,
            missing_envelope=self.panel_missing_envelope,
            planned_pages=self.total_pages,
            completed_pages=self.completed_pages,
            failed_pages=self.failed_pages,
            unique_rows=self.total_elements,
            duplicates=self.duplicates_dropped,
        )

    async def _fetch_segmented(self) -> AsyncIterator[RawRecord]:
        assert self._frontier is not None
        await self._load_robots()
        seen: set[str] = set()
        self.total_pages = 0
        self.completed_pages = 0

        for segment in self._frontier.pending(min_level=self._min_level):
            if self._max_segments is not None and self.segments_processed >= self._max_segments:
                break

            self.active_segment = segment
            try:
                if segment.level == 0:
                    # Unscoped national catch-all: walk fully. It is the only
                    # source of the non-geographic tail (Verschiedene
                    # Arbeitsorte / Deutschland / Bundesweit).
                    async for rec in self._walk_segment(segment, seen):
                        yield rec
                    if segment.status == "truncated":
                        self._subdivide_segment(segment)
                elif segment.level == 1:
                    # Bundesland: structural truncation probe (page 400 full =>
                    # >10k postings, provably truncated). Either way it ends
                    # ``subdivided``: its municipality children (already seeded
                    # at level 2) are the collection units, so no Bundesland
                    # pages are walked — a walk would duplicate municipality
                    # rows at ~2 h of runtime for zero marginal NUTS-3 breadth.
                    truncated = await self._truncation_probe(segment)
                    if truncated:
                        self.segments_truncated += 1
                    self._subdivide_segment(segment)
                else:
                    # Level 2 (municipalities / PLZ backbone) and level 3/4
                    # (subdivision children): walk fully with the oracle.
                    async for rec in self._walk_segment(segment, seen):
                        yield rec
                    if segment.status == "truncated":
                        self._subdivide_segment(segment)
            except RuntimeError:
                # Schema drift and hard blocks are systemic — fail loudly,
                # never mark a segment failed and continue collecting garbage.
                raise
            except Exception as exc:  # noqa: BLE001
                self._log.error("ba_segment_failed", key=segment.key, error=str(exc))
                segment.status = "failed"
                self.segments_failed += 1

            self.segments_processed += 1
            self.active_segment = None
            self._frontier.save(self._frontier_path)

        self.total_elements = len(seen)
        self.total_pages = self.completed_pages  # reconcile the manifest
        self._log.info(
            "ba_segmented_sweep_summary",
            search_pages=self.completed_pages,
            segments_processed=self.segments_processed,
            segments_complete=self.segments_complete,
            segments_truncated=self.segments_truncated,
            segments_subdivided=self.segments_subdivided,
            segments_failed=self.segments_failed,
            items=self.items_seen,
            unique_rows=self.total_elements,
            duplicates=self.duplicates_dropped,
        )

    async def _truncation_probe(self, segment: Segment) -> bool:
        """Fetch page ``BA_MAX_QUERY_PAGES`` once; 25 items proves truncation."""
        url = self._segment_url(segment.key, BA_MAX_QUERY_PAGES)
        response = await self._get(url)
        if response.status_code != 200:
            return False
        items = parse_page(response.text)
        segment.pages_fetched += 1
        self.completed_pages += 1
        return len(items) == BA_ITEMS_PER_PAGE

    def _subdivide_segment(self, segment: Segment) -> None:
        """Enqueue child segments for a truncated node, then mark subdivided."""
        assert self._frontier is not None
        level = segment.level
        children: list[Segment] = []

        if level == 0:
            # Children = 16 Bundesländer.
            for name, nuts1 in BA_BUNDESLAENDER.items():
                from urllib.parse import quote

                children.append(
                    Segment(
                        key=f"wo={quote(name)}&umkreis={self._umkreis}",
                        level=1,
                        nuts_code=None,
                        nuts1=nuts1,
                        parent=segment.key,
                        umkreis=self._umkreis,
                    )
                )
        elif level == 1:
            # Children = the municipality segments whose NUTS-1 prefix matches.
            # Those are already seeded at level 2 from ``build_initial_frontier``,
            # so enqueue is a no-op; kept for the tree's structural completeness.
            for child in self._frontier.segments.values():
                if child.level == 2 and child.nuts1 == segment.nuts1:
                    children.append(child)
        elif level == 2 and segment.nuts_code:
            # PLZ sub-segments inside this NUTS 3 (the crosswalk's PLZ rows).
            for plz in self._crosswalk.plz_codes_for_nuts(segment.nuts_code):
                children.append(
                    Segment(
                        key=f"wo={plz}&umkreis={self._umkreis}",
                        level=3,
                        nuts_code=segment.nuts_code,
                        nuts1=segment.nuts1,
                        parent=segment.key,
                        umkreis=self._umkreis,
                    )
                )
        elif level == 3:
            # Level-4 recency slices for a still-truncating PLZ.
            for days in BA_LEVEL4_RECENCY_DAYS:
                children.append(
                    Segment(
                        key=f"{segment.key}&veroeffentlichtseit={days}",
                        level=4,
                        nuts_code=segment.nuts_code,
                        nuts1=segment.nuts1,
                        parent=segment.key,
                        umkreis=self._umkreis,
                        recency_days=days,
                    )
                )

        for child in children:
            self._frontier.enqueue(child)
        segment.status = "subdivided"
        self.segments_subdivided += 1

    async def _walk_segment(
        self,
        segment: Segment,
        seen: set[str],
    ) -> AsyncIterator[RawRecord]:
        """Walk pages of one segment until complete or truncated.

        Oracle: a segment is *complete* iff its pagination ends with an empty
        (or sub-25) page at P ≤ 400; a *full* 400th page proves truncation.
        Schema drift is detected only where emptiness is abnormal (level 0/1
        page 1); a level-2+ segment with no postings is legitimately complete.
        """
        for page_num in range(1, BA_MAX_QUERY_PAGES + 1):
            url = self._segment_url(segment.key, page_num)
            response = await self._get(url)
            if response.status_code != 200:
                self.failed_pages += 1
                self._log.warning("ba_page_failed", url=url, status=response.status_code)
                continue
            self.completed_pages += 1
            segment.pages_fetched += 1

            items = parse_page(response.text)
            if not items:
                self.empty_pages += 1
                if page_num == 1 and segment.level in (0, 1):
                    raise RuntimeError(
                        f"BA Jobsuche segment {segment.key!r} page 1 returned 0 results — "
                        "the page structure may have changed (schema drift)"
                    )
                segment.last_page_full = False
                segment.status = "complete"
                self.segments_complete += 1
                break

            self.items_seen += len(items)
            is_full = len(items) == BA_ITEMS_PER_PAGE

            for item in items:
                source_id = pseudonymize(item.native_id, self._hmac_key)
                if source_id in seen:
                    self.duplicates_dropped += 1
                    continue
                seen.add(source_id)
                segment.rows_yielded += 1
                yield RawRecord(
                    native_id=item.native_id,
                    payload={
                        "native_id": item.native_id,
                        "first_published": item.first_published,
                        "location_city": item.location_city,
                        "segment_key": segment.key,
                        "segment_nuts3": segment.nuts_code,
                        "segment_nuts1": segment.nuts1,
                        "segment_level": segment.level,
                        "umkreis": self._umkreis,
                    },
                )

            if not is_full:
                segment.last_page_full = False
                segment.status = "complete"
                self.segments_complete += 1
                break

            if page_num == BA_MAX_QUERY_PAGES:
                segment.last_page_full = True
                segment.status = "truncated"
                self.segments_truncated += 1
                break

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
            "segment_nuts3": raw.payload.get("segment_nuts3"),
            "segment_nuts1": raw.payload.get("segment_nuts1"),
            "segment_level": raw.payload.get("segment_level"),
            "umkreis": raw.payload.get("umkreis", 0),
        }

    def normalize(self, parsed: dict[str, Any]) -> NormalizedRecord:
        # Tier 1 (municipality crosswalk, comma-qualifier strip/alias) and
        # Tier 2 (segment-context disambiguation of an ambiguous city).
        region = self._crosswalk.resolve_by_city_segmented(
            parsed["location_city"],
            segment_nuts1=parsed.get("segment_nuts1"),
            segment_nuts3=parsed.get("segment_nuts3"),
        )
        # Tier 3 (segment provenance): a posting collected under a single-NUTS-3
        # segment with umkreis=0 is ``mapped`` by the source's own location
        # filter; a radius downgrades it to ``low_confidence`` (map-excluded).
        # Non-geographic markers and Tier-1/2 ambiguous results are never
        # overridden — the source stated a multi-location/nationwide workplace.
        if region.status == "unmapped" and parsed.get("segment_nuts3"):
            # The segment's own code resolves the region; the label comes from the
            # same reference so the resolution is complete (Increment 20b: the two
            # Tier-3 paths previously published the code with a null label).
            segment_label = self._crosswalk.label_for_nuts(parsed["segment_nuts3"])
            if parsed.get("umkreis") == 0:
                region = RegionResolution(
                    nuts_code=parsed["segment_nuts3"],
                    nuts_label=segment_label,
                    status="mapped",
                    method="ba_segment_provenance_nuts3",
                )
            else:
                region = RegionResolution(
                    nuts_code=parsed["segment_nuts3"],
                    nuts_label=segment_label,
                    status="low_confidence",
                    method="ba_segment_radius_nuts3",
                )
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
