"""VDAB collector — SCRAPER_ROADMAP.md Increment 5 (Belgium — Flanders).

VDAB's public job-search **website**, not its API. The Vacature API v4 is
**blocked** (an approved partnership plus a signed *samenwerkingsovereenkomst*)
and is deliberately **not** routed around; see `SCRAPER_FEASIBILITY.md`
Increment 5 Surface A. The implemented surface is Surface B: the server-rendered
SEO landing pages VDAB publishes in its own sitemaps.

    GET https://www.vdab.be/robots.txt
    GET https://www.vdab.be/vindeenjob/jobs/nc/sitemap/sitemap.xml   -> 4 keyword sitemaps
    GET https://www.vdab.be/vindeenjob/jobs/nc/sitemap/keyword-0.xml -> 10,000 landing pages
    GET https://www.vdab.be/vindeenjob/jobs/<postcode>-<gemeente>    -> 28 vacancy tiles

Contract pinned live on 2026-08-22 and re-verified on the same day before this
sweep:

- **robots.txt is the gate, and it is enforced per URL.** ``robots.txt``
  advertises six sitemaps (so crawling the listed surfaces is invited) and has no
  ``Crawl-Delay`` for ``*``. It **disallows** ``/api/vindeenjob/`` — the Angular
  app's own JSON API and the path every public third-party VDAB scraper uses —
  plus ``/vacatures/``, ``/include/vacature/``, ``/zoeken/``, ``/tv-zoeken/``,
  ``/vindeenjob/prive/``, ``/mijnvdab/``, ``/vac/`` and ``/prive/``. Every URL
  this collector requests is checked with :class:`~scrapers.robots.RobotsRule`
  first and a disallowed URL raises :class:`RobotsDisallowedError` instead of
  being skipped silently.
- **Discovery, not guessing.** Landing pages come from the keyword sitemaps and
  are filtered to the ``<postcode>-<gemeente>`` slugs (2,251 of the 10,000 URLs
  in ``keyword-0.xml``), because the postcode prefix is what resolves the region
  dimension.
- **No in-page pagination.** ``?limit=100``, ``?page=2`` and ``?start=15`` all
  return the byte-identical 28-tile page and ``/2`` answers 404 (re-probed live);
  deeper paging is a client-side call into the disallowed ``/api/vindeenjob/``.
  Coverage therefore comes from **breadth** (many landing pages), never from
  fabricated pagination parameters — this collector sends none.
- **No server-rendered detail page.** ``/vindeenjob/vacatures`` and every
  ``/vindeenjob/vacatures/<id>/<slug>`` return the same ~46 KB Angular shell with
  zero ``ld+json`` blocks, so per-vacancy enrichment is impossible from HTML and
  is not attempted.
- **No anti-bot.** No Cloudflare/Akamai/Incapsula headers and no challenge, with
  one stable, honest, contactable user-agent. The roadmap's "randomized
  user-agents" canary clause is deliberately **not** applied: identity obscuring
  contradicts the charter and drew zero blocks without it (documented deviation
  in `SCRAPER_FEASIBILITY.md`).

SAFE_FIELDS mapping:

- ``source_id``        = HMAC of the numeric vacancy id in the tile's
  ``/vindeenjob/vacatures/<id>/<slug>`` link. Tiles repeat across landing pages
  (measured: 255 tiles -> 189 unique ids in the canary), so rows are deduped on
  the HMAC digest, never on the native id.
- ``first_published``  = the tile's ``Online sinds <d mmm. yyyy>`` Dutch date
  (date-only at source; stored at 00:00 UTC).
- ``last_modified``    = ``None``. The weekly vacancy sitemaps do carry a
  per-URL ``<lastmod>``, but they are historic ISO-week slices (probed live:
  214 children spanning week 25/2024 onwards) whose ids largely do not intersect
  the current tiles, so joining them would cost 214 extra requests for a partial
  join of a sitemap-generation timestamp. Skipped on purpose, not overlooked.
- ``removed_at``       = ``None``; not exposed. Closures are absence-based across
  sweeps (deferred, as in Increments 3-4).
- ``number_of_vacancies`` = 1; the tiles expose no per-posting count.
- **Region:** the landing-page slug's postcode is resolved through the pinned
  ``data/reference/vdab_postcode_nuts_2024.csv`` (Basisregisters Vlaanderen
  ``postinfo/{postcode}.nuts3``, validated against Eurostat GISCO NUTS 2024) ->
  ``mapped``; a postcode outside the Flemish register (Brussels ``1000`` answers
  ``410 Verwijderde postcode``, foreign slugs such as ``1011-amsterdam``) ->
  ``unmapped``. The postcode is the *search segment's* location, so the mapped
  region is the municipality the vacancy was advertised for — recorded in
  ``coverage_limitations``.
- **Occupation:** the tiles carry only a free-text title and a contract-type
  label, i.e. no ROME/C2/ISCO code at all, so the status is ``not_present``
  (Increments 1-3 precedent) with method ``not_available_vdab_html`` — not the
  ``unmapped`` of Increment 4, where a source code existed but its crosswalk did
  not.

PII and licence compliance: each tile also renders a job title
(``h2.product-title``), the employer and city (``.location-job``), a description
snippet (``.product-description``), a company logo (``.company-logo``) and a deep
link with tracking parameters. **None of them are read.** The parse is
allowlist-only — it extracts the numeric id and the ``Online sinds`` label and
nothing else — ``VacancyTile(extra="forbid")`` and
``NormalizedRecord(extra="forbid")`` are the backstops, and the postcode is used
transiently to derive NUTS 3 and never persisted (Increment 4 precedent). The
vdab.be disclaimer permits copying and using site information for informational
purposes but protects the VDAB name and logo as trademarks, so no brand,
employer or logo string is ever written to disk.
"""

from __future__ import annotations

import csv
import hashlib
import re
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Final

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, ConfigDict, Field

from scrapers.base import (
    REQUEST_TIMEOUT_SECONDS,
    BaseCollector,
    MappingStatus,
    NormalizedRecord,
    RawRecord,
)
from scrapers.retry import RetryPolicy, with_backoff
from scrapers.robots import PacingGate, RobotsDisallowedError, RobotsRule
from scrapers.sanitize import pseudonymize

VDAB_BASE = "https://www.vdab.be"
VDAB_ROBOTS_URL = f"{VDAB_BASE}/robots.txt"
#: Sitemap index of the keyword/location landing pages (advertised in robots.txt).
VDAB_KEYWORD_SITEMAP_URL = f"{VDAB_BASE}/vindeenjob/jobs/nc/sitemap/sitemap.xml"
#: Weekly vacancy sitemaps (ids + <lastmod>); documented, deliberately unused.
VDAB_VACANCY_SITEMAP_URL = f"{VDAB_BASE}/sitemap/vindeenjob/vacatures/index.xml"
#: The Angular app's internal JSON API. robots-DISALLOWED; never requested.
VDAB_FORBIDDEN_API_PATH = "/api/vindeenjob/"

VDAB_SOURCE_VERSION = "vindeenjob-html-2026-08"
VDAB_SCOPE_ID = "be-flanders-all-active"
VDAB_SCOPE_PARAMS: dict[str, str] = {
    "source": "vdab",
    "country": "BE",
    "region": "flanders",
    "surface": "public-html-landing-pages",
    "query": "all-active",
    "segmentation": "postcode-landing-page",
}
VDAB_LICENCE_REFERENCE = "https://www.vdab.be/disclaimer"
VDAB_ACCESS_METHOD = "robots-permitted-html"
#: Public job board refreshed continuously; a daily sweep is the freshness target.
VDAB_FRESHNESS_THRESHOLD_HOURS = 24

#: Charter floor is 1 s; the canary ran at 1.2 s and drew zero blocks, so the
#: collector keeps that slower pace.
VDAB_PACING_SECONDS = 1.2
#: Tiles rendered per landing page (fixed by the server; no pagination exists).
VDAB_TILES_PER_PAGE = 28
#: Default sweep breadth: one landing page per distinct Flemish postcode (the
#: keyword sitemaps publish 499 of them) plus a little slack. Breadth ordering
#: makes this the widest geographic sample per request — it reaches all 22
#: Flemish NUTS 3 arrondissements and clears the Definition of Done's 5,000 rows
#: at ~28 tiles per page. Every page is one paced request (~10 min at 1.2 s).
VDAB_DEFAULT_PAGE_BUDGET = 500

VDAB_USER_AGENT = (
    "EU-Tech-Labour-Observatory/0.1 (+public job-data research, robots-and-ToS-compliant, "
    "vdab.be disclaimer: informational re-use)"
)

VDAB_REFERENCE_FILE = "vdab_postcode_nuts_2024.csv"

#: Advertised active Flemish stock on the search page (live 2026-08-22).
VDAB_ADVERTISED_FLANDERS_STOCK = 232944
#: Postcode-prefixed landing pages published in the keyword sitemaps.
VDAB_PUBLISHED_LANDING_PAGES = 34903

VDAB_COVERAGE_LIMITATIONS = (
    "Public server-rendered job-search website of VDAB (Flanders only; Wallonia's "
    "Le Forem and Brussels' Actiris are separate services and out of scope). The "
    "Vacature API v4 is blocked (VDAB-approved partnership + signed "
    "samenwerkingsovereenkomst) and is not routed around, and the Angular app's "
    "internal JSON API (/api/vindeenjob/) is robots-disallowed and never "
    "requested. Landing pages are discovered from the keyword sitemaps VDAB "
    f"advertises in robots.txt ({VDAB_PUBLISHED_LANDING_PAGES} published URLs, of "
    "which this sweep uses the postcode-prefixed ones). **Coverage gap, stated "
    f"plainly:** the search page advertises {VDAB_ADVERTISED_FLANDERS_STOCK} active "
    f"Flemish vacancies; each landing page renders at most its first "
    f"{VDAB_TILES_PER_PAGE} tiles and has no working pagination (?limit, ?page and "
    "?start are ignored, /2 returns 404 — probed live), so a sweep sees "
    f"{VDAB_TILES_PER_PAGE} x (landing pages fetched) tiles before dedupe and full "
    "coverage would require walking a large share of the published landing pages. "
    "This is a breadth sample of the active stock, not a complete snapshot. Tiles "
    "repeat across landing pages and are deduped on HMAC source_id. Region is "
    "derived from the landing page's postcode via the pinned Basisregisters "
    "Vlaanderen postcode -> NUTS 2024 crosswalk, so it is the municipality the "
    "vacancy was advertised for; postcodes outside the Flemish register (Brussels, "
    "foreign slugs) stay unmapped. Occupation is not present on the public tiles "
    "(no ROME/C2/ISCO code). last_modified is not collected: the weekly vacancy "
    "sitemaps carry a per-URL <lastmod> but are historic ISO-week slices whose "
    "ids largely do not intersect the current tiles. removed_at is not exposed; "
    "closures are absence-based across consecutive sweeps."
)

SITEMAP_NS: Final = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

#: ``https://www.vdab.be/vindeenjob/jobs/1000-brussel-stad`` -> ``1000``.
_LANDING_POSTCODE = re.compile(r"/vindeenjob/jobs/([1-9]\d{3})-[^/]+$")
#: ``/vindeenjob/vacatures/74399985/industrieel-ingenieur?...`` -> ``74399985``.
_VACANCY_ID = re.compile(r"/vindeenjob/vacatures/(\d+)/")
#: ``Online sinds  15 aug. 2026`` -> ``15``, ``aug``, ``2026``.
_ONLINE_SINDS = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})")
#: ``<div class="numbers-job"><strong>1627</strong><span>jobs gevonden``.
_ADVERTISED_TOTAL_SELECTOR = ".numbers-job strong"

#: Dutch month names as rendered on the tiles, abbreviated and full.
DUTCH_MONTHS: Final[dict[str, int]] = {
    "jan": 1,
    "januari": 1,
    "feb": 2,
    "februari": 2,
    "mrt": 3,
    "maart": 3,
    "apr": 4,
    "april": 4,
    "mei": 5,
    "jun": 6,
    "juni": 6,
    "jul": 7,
    "juli": 7,
    "aug": 8,
    "augustus": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "okt": 10,
    "oktober": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


#: ``RobotsDisallowedError`` now lives in :mod:`scrapers.robots` (shared by every
#: collector that gates its requests per URL, Increment 6 onwards) and is
#: imported above, so ``from scrapers.vdab import RobotsDisallowedError`` keeps
#: working and both collectors raise the *same* class.


# ---------------------------------------------------------------------------
# Discovery and parsing
# ---------------------------------------------------------------------------


def sitemap_locations(xml_text: str) -> list[str]:
    """Every ``<loc>`` in a sitemap index or urlset, in document order."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    return [(node.text or "").strip() for node in root.iter(f"{SITEMAP_NS}loc") if node.text]


def landing_postcode(url: str) -> str | None:
    """The four-digit postcode prefix of a landing-page slug, or None.

    ``.../vindeenjob/jobs/1000-brussel-stad`` -> ``1000``; keyword pages without
    a postcode prefix (``.../jobs/verpleegkundige``) return None and are skipped
    because they carry no region signal.
    """
    match = _LANDING_POSTCODE.search(url.split("?", 1)[0].rstrip("/"))
    return match.group(1) if match else None


def order_by_postcode_breadth(pages: Sequence[str]) -> list[str]:
    """Interleave landing pages so distinct postcodes come first.

    Sitemap order is postcode-ascending with several slug variants per postcode
    (``1500-halle``, ``1500-halle-deeltijds``, ``1500-halle-vlaams-brabant-provincie``),
    so a budgeted prefix of it would sample one small corner of Flanders and
    re-see the same vacancies. Round-robining over postcodes puts one page per
    postcode first, which maximizes geographic spread, NUTS 3 diversity and the
    unique-vacancy yield per paced request. The order is deterministic.
    """
    buckets: dict[str, list[str]] = {}
    for url in pages:
        buckets.setdefault(landing_postcode(url) or "", []).append(url)
    depth = max((len(bucket) for bucket in buckets.values()), default=0)
    ordered: list[str] = []
    for index in range(depth):
        for postcode in sorted(buckets):
            bucket = buckets[postcode]
            if index < len(bucket):
                ordered.append(bucket[index])
    return ordered


def parse_dutch_date(value: str | None) -> datetime | None:
    """Parse a tile's ``Online sinds <d mmm. yyyy>`` label into a UTC datetime.

    Total by construction: an unparseable label (missing, English, a relative
    phrase, garbage, or an impossible date such as 31 February) returns None
    rather than a guess. The source reports a date only, stored at 00:00 UTC.
    """
    if not value:
        return None
    match = _ONLINE_SINDS.search(value)
    if match is None:
        return None
    month = DUTCH_MONTHS.get(match.group(2).lower())
    if month is None:
        return None
    try:
        return datetime(int(match.group(3)), month, int(match.group(1)), tzinfo=UTC)
    except ValueError:
        return None


class VacancyTile(BaseModel):
    """The allowlist-relevant slice of one server-rendered vacancy tile.

    ``extra="forbid"`` keeps the tile's title, employer, city, description
    snippet, logo and deep link out of the pipeline by construction: only the
    numeric id and the ``Online sinds`` label are ever read.
    """

    model_config = ConfigDict(extra="forbid")

    native_id: str = Field(min_length=1)
    online_since: str | None = None


class LandingPage(BaseModel):
    """One parsed landing page: its postcode, advertised total and tiles."""

    model_config = ConfigDict(extra="forbid")

    postcode: str | None = None
    advertised_total: int | None = None
    tiles: list[VacancyTile] = Field(default_factory=list)
    #: Tile containers whose markup carried no resolvable vacancy id.
    tiles_without_id: int = 0


def _tile_native_id(tile: Tag) -> str | None:
    """The numeric vacancy id from the tile's link, or None for a malformed tile."""
    for link in tile.select("a[href]"):
        href = link.get("href")
        if not isinstance(href, str):
            continue
        match = _VACANCY_ID.search(href)
        if match:
            return match.group(1)
    return None


def _tile_online_since(tile: Tag) -> str | None:
    """The tile's ``Online sinds`` label (a date, not free text), or None.

    Whitespace is collapsed because the server renders ``Online sinds  15 aug.
    2026`` with a double space.
    """
    node = tile.select_one(".online-sinds")
    if node is None:
        return None
    return " ".join(node.get_text(" ", strip=True).split()) or None


def _advertised_total(soup: BeautifulSoup) -> int | None:
    """The segment total the page advertises (``<strong>1627</strong> jobs gevonden``)."""
    node = soup.select_one(_ADVERTISED_TOTAL_SELECTOR)
    if node is None:
        return None
    digits = re.sub(r"\D", "", node.get_text(strip=True))
    return int(digits) if digits else None


def parse_landing_page(html: str, *, postcode: str | None = None) -> LandingPage:
    """Allowlist-only parse of one landing page's vacancy tiles (28 on a full page).

    Reads exactly two things per tile — the numeric id and the ``Online sinds``
    label — and ignores the title, employer, city, description snippet, logo and
    tracking parameters that share the same markup. Tiles without a resolvable
    id are dropped (and counted by the caller) instead of yielding a row with a
    fabricated identifier.
    """
    soup = BeautifulSoup(html, "lxml")
    tiles: list[VacancyTile] = []
    without_id = 0
    for node in soup.select("div.product-tile"):
        native_id = _tile_native_id(node)
        if native_id is None:
            without_id += 1
            continue
        tiles.append(VacancyTile(native_id=native_id, online_since=_tile_online_since(node)))
    return LandingPage(
        postcode=postcode,
        advertised_total=_advertised_total(soup),
        tiles=tiles,
        tiles_without_id=without_id,
    )


# ---------------------------------------------------------------------------
# Region crosswalk (NUTS 2024)
# ---------------------------------------------------------------------------


class RegionResolution(BaseModel):
    """Outcome of the postcode -> NUTS 2024 resolution for one landing page."""

    nuts_code: str | None = None
    nuts_label: str | None = None
    status: MappingStatus = "unmapped"
    method: str = "not_available"


class VDABCrosswalk:
    """Loads the pinned Flemish postcode -> NUTS 2024 table and resolves regions.

    A postcode present in Basisregisters Vlaanderen resolves to ``mapped``;
    anything else (Brussels' ``1000``, which the Flemish register answers with
    ``410 Verwijderde postcode``, or a foreign slug such as ``1011-amsterdam``)
    stays ``unmapped``.
    """

    def __init__(self, reference_dir: Path) -> None:
        path = reference_dir / VDAB_REFERENCE_FILE
        if not path.exists():
            raise FileNotFoundError(
                f"missing VDAB crosswalk reference: {path} "
                "(rebuild with `python -m scrapers.reference_vdab`)"
            )
        self._mapping: dict[str, tuple[str, str]] = {}
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                self._mapping[row["source_code"].strip()] = (row["nuts_code"], row["nuts_label"])
        if not self._mapping:
            raise ValueError(f"VDAB crosswalk reference is empty: {path}")

    def postcodes(self) -> list[str]:
        """The Flemish postcodes the crosswalk knows (sorted, stable)."""
        return sorted(self._mapping)

    def resolve(self, postcode: str | None) -> RegionResolution:
        hit = self._mapping.get((postcode or "").strip())
        if hit is None:
            return RegionResolution(method="not_available")
        return RegionResolution(
            nuts_code=hit[0],
            nuts_label=hit[1],
            status="mapped",
            method="vdab_landing_postcode_nuts3",
        )


def crosswalk_reference_hashes(reference_dir: Path) -> str:
    """SHA-256 of the pinned crosswalk CSV (content only)."""
    digest = hashlib.sha256()
    with (reference_dir / VDAB_REFERENCE_FILE).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return f"{VDAB_REFERENCE_FILE}:{digest.hexdigest()}"


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class VDABCollector(BaseCollector):
    """Collector for VDAB's public job-search website (Belgium — Flanders).

    Fetches and parses ``robots.txt`` once, then checks **every** URL against it
    before requesting it, discovers postcode landing pages from the keyword
    sitemaps, and walks them at the charter's pacing floor. Coverage is
    breadth-based: no pagination parameter is ever sent because the server
    ignores all of them.
    """

    source: ClassVar[str] = "vdab"
    country: ClassVar[str] = "BE"

    def __init__(
        self,
        *,
        scope_id: str,
        sweep_id: str,
        observed_at: datetime,
        hmac_key: bytes,
        reference_dir: Path = Path("data/reference"),
        max_pages: int | None = None,
        landing_pages: Sequence[str] | None = None,
        flemish_only: bool = True,
        pacing_interval: float = VDAB_PACING_SECONDS,
        policy: RetryPolicy | None = None,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            scope_id=scope_id, sweep_id=sweep_id, observed_at=observed_at, timeout=timeout
        )
        if len(hmac_key) < 32:
            raise ValueError("hmac_key must be at least 32 bytes")
        self._hmac_key = hmac_key
        self._crosswalk = VDABCrosswalk(reference_dir)
        self._page_budget = VDAB_DEFAULT_PAGE_BUDGET if max_pages is None else max(1, max_pages)
        self._landing_pages = list(landing_pages) if landing_pages is not None else None
        self._flemish_only = flemish_only
        self._policy = policy or RetryPolicy()
        self._pacer = PacingGate(min_interval=pacing_interval)
        self._pacing_interval = pacing_interval
        self._robots: RobotsRule | None = None
        self._headers = {"User-Agent": VDAB_USER_AGENT, "Accept": "text/html,application/xml"}
        self.total_elements = 0
        self.total_pages = 0
        self.completed_pages = 0
        #: Postcode-prefixed landing pages discovered in the keyword sitemaps.
        self.landing_pages_available = 0
        #: Tiles parsed across all landing pages, before dedupe.
        self.tiles_seen = 0
        #: Tiles dropped because their HMAC source_id was already collected.
        self.duplicates_dropped = 0
        #: Tiles whose markup carried no resolvable vacancy id.
        self.tiles_without_id = 0
        #: Landing pages that answered non-200 after retries (DoD: must stay 0).
        self.failed_pages = 0
        #: Largest per-segment total any fetched landing page advertised.
        self.max_advertised_total: int | None = None

    # -- robots gate --------------------------------------------------------

    async def _load_robots(self) -> RobotsRule:
        """Fetch and parse ``robots.txt`` once per sweep (before any other URL)."""
        if self._robots is not None:
            return self._robots

        async def do_get() -> httpx.Response:
            return await self._client.get(VDAB_ROBOTS_URL, headers=self._headers)

        await self._pacer.wait()
        response = await with_backoff(self._policy)(do_get)()
        # An absent robots.txt allows everything; a served one is authoritative.
        text = response.text if response.status_code == 200 else None
        rule = RobotsRule(text)
        self._robots = rule
        delay = rule.crawl_delay(VDAB_USER_AGENT)
        self._log.info(
            "vdab_robots_loaded",
            status=response.status_code,
            bytes=len(response.content),
            crawl_delay=delay,
            api_path_allowed=rule.can_fetch(VDAB_BASE + VDAB_FORBIDDEN_API_PATH, VDAB_USER_AGENT),
        )
        if delay is not None and delay > self._pacing_interval:
            self._pacer = PacingGate(min_interval=delay)
        return rule

    def assert_allowed(self, url: str) -> None:
        """Raise :class:`RobotsDisallowedError` unless robots.txt permits ``url``.

        The hard failure is the point: the sweep must stop loudly rather than
        quietly omit a surface it is not allowed to read.
        """
        rule = self._robots
        if rule is None:
            raise RobotsDisallowedError(f"robots.txt not loaded before requesting {url}")
        if not rule.can_fetch(url, VDAB_USER_AGENT):
            raise RobotsDisallowedError(f"robots.txt disallows {url} for {VDAB_USER_AGENT}")

    async def _get(self, url: str) -> httpx.Response:
        """One paced, retried, robots-checked GET. No query parameters are added."""
        self.assert_allowed(url)

        async def do_get() -> httpx.Response:
            return await self._client.get(url, headers=self._headers)

        await self._pacer.wait()
        return await with_backoff(self._policy)(do_get)()

    # -- discovery ----------------------------------------------------------

    async def discover_landing_pages(self) -> list[str]:
        """Postcode-prefixed landing pages from the keyword sitemaps.

        Child sitemaps are read only until the page budget is covered (each holds
        10,000 URLs, ~2,251 of them postcode-prefixed and ~1,926 with a Flemish
        postcode), so a small sweep does not download 5 MB of XML it cannot use.
        The result is breadth-ordered by postcode (see
        :func:`order_by_postcode_breadth`).
        """
        if self._landing_pages is not None:
            self.landing_pages_available = len(self._landing_pages)
            return self._landing_pages

        index = await self._get(VDAB_KEYWORD_SITEMAP_URL)
        index.raise_for_status()
        children = sitemap_locations(index.text)
        self._log.info("vdab_sitemap_index", children=len(children))

        pages: list[str] = []
        seen: set[str] = set()
        for child in children:
            response = await self._get(child)
            response.raise_for_status()
            for url in sitemap_locations(response.text):
                postcode = landing_postcode(url)
                if postcode is None or url in seen:
                    continue
                if self._flemish_only and not self._crosswalk.resolve(postcode).nuts_code:
                    continue
                seen.add(url)
                pages.append(url)
            self._log.info("vdab_sitemap_child", child=child, landing_pages=len(pages))
            if len(pages) >= self._page_budget:
                break
        self.landing_pages_available = len(pages)
        return order_by_postcode_breadth(pages)

    # -- fetch --------------------------------------------------------------

    def fetch(self) -> AsyncIterator[RawRecord]:
        """Walk the budgeted landing pages, yielding one RawRecord per unique tile."""
        return self._fetch()

    async def _fetch(self) -> AsyncIterator[RawRecord]:
        await self._load_robots()
        pages = (await self.discover_landing_pages())[: self._page_budget]
        self.total_pages = len(pages)
        seen: set[str] = set()

        for url in pages:
            response = await self._get(url)
            if response.status_code != 200:
                self.failed_pages += 1
                self._log.warning("vdab_page_failed", url=url, status=response.status_code)
                continue
            self.completed_pages += 1
            postcode = landing_postcode(url)
            page = parse_landing_page(response.text, postcode=postcode)
            if page.advertised_total is not None:
                self.max_advertised_total = max(
                    page.advertised_total, self.max_advertised_total or 0
                )
            tiles = len(page.tiles)
            self.tiles_seen += tiles
            self.tiles_without_id += page.tiles_without_id
            for tile in page.tiles:
                source_id = pseudonymize(tile.native_id, self._hmac_key)
                if source_id in seen:
                    self.duplicates_dropped += 1
                    continue
                seen.add(source_id)
                yield RawRecord(
                    native_id=tile.native_id,
                    payload={**tile.model_dump(), "postcode": postcode},
                )

        self.total_elements = len(seen)
        self._log.info(
            "vdab_sweep_summary",
            landing_pages=self.completed_pages,
            planned_pages=self.total_pages,
            failed_pages=self.failed_pages,
            tiles=self.tiles_seen,
            unique_rows=self.total_elements,
            duplicates=self.duplicates_dropped,
        )

    # -- normalization ------------------------------------------------------

    def parse(self, raw: RawRecord) -> dict[str, Any]:
        """Extract the source-native fields the allowlist needs from one tile."""
        tile = VacancyTile.model_validate(
            {"native_id": raw.payload["native_id"], "online_since": raw.payload.get("online_since")}
        )
        return {
            "native_id": tile.native_id,
            "first_published": parse_dutch_date(tile.online_since),
            "postcode": raw.payload.get("postcode"),
        }

    def normalize(self, parsed: dict[str, Any]) -> NormalizedRecord:
        """Map parsed fields onto the SAFE_FIELDS allowlist and pseudonymize the id."""
        region = self._crosswalk.resolve(parsed["postcode"])
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
            occupation_mapping_method="not_available_vdab_html",
            source_language="nl",
            jobtech_taxonomy_version="",
            esco_version="1.2.1",
            skill_mappings=[],
            lang="nl",
            number_of_vacancies=1,
        )
