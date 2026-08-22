"""Adzuna multi-country collector — SCRAPER_ROADMAP.md Increment 3.

Official keyed public REST API (developer.adzuna.com):

    GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
    query app_id=...&app_key=...&results_per_page=50&content-type=application/json

Response envelope (``Adzuna::API::Response::JobSearchResults``):

    {"__CLASS__": "...", "count": N, "results": [ {...}, ... ]}

One collector serves all 18 country domains: the country code, locale, language,
expected country and scope live in :class:`CountryAdapter` (DE and NL adapters
shipped; others are one config object away). Pagination is the trailing path
segment (``/search/1``, ``/search/2``, ...); the free tier is throttled
(ToS: 25 hits/min, 250 hits/day, 1000/week, 2500/month) so the collector paces
at >= 2.5 s and honors ``Retry-After`` on 429s via ``scrapers.retry``.

SAFE_FIELDS mapping:

- ``source_id``    = HMAC of the native ad ``id`` (the adref; Adzuna's own id
  for a listing in its aggregated index). The same role posted by several
  source boards appears as distinct Adzuna ads with distinct ids — cross-board
  merge is not possible from the search payload, recorded as a coverage
  limitation.
- ``first_published`` = ``created`` (ISO 8601 UTC). ``last_modified`` /
  ``removed_at`` are not in the search payload; absent (absence-based closure
  stamping across sweeps is deferred, as in Increments 1-2).
- ``number_of_vacancies`` = 1 (Adzuna exposes no per-posting counts).
- Region: Adzuna exposes ``location.area[]`` / ``display_name`` free text only,
  no region/NUTS codes -> ``region_mapping_status=not_present`` for this
  increment (a pinned area-name -> NUTS 2024 crosswalk is a later candidate,
  recorded in SCRAPER_FEASIBILITY.md).
- Occupation: Adzuna ``category`` (label/tag) -> ESCO deferred
  (``occupation_mapping_status=not_present``), as in Increments 1-2.

PII: ``title``, ``description``, ``company``, contacts, ``redirect_url`` and
any free text exist in the raw payload but are excluded by the allowlist-only
parse plus ``NormalizedRecord(extra="forbid")``.
"""

from __future__ import annotations

import math
import os
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from scrapers.base import REQUEST_TIMEOUT_SECONDS, BaseCollector, NormalizedRecord, RawRecord
from scrapers.retry import RetryPolicy, with_backoff
from scrapers.robots import PacingGate
from scrapers.sanitize import pseudonymize, read_dotenv_value

ADZUNA_API_BASE = "https://api.adzuna.com/v1/api/jobs"
ADZUNA_SOURCE_VERSION = "adzuna-api-v1"
ADZUNA_ACCESS_METHOD = "public-api"
ADZUNA_FRESHNESS_THRESHOLD_HOURS = 24
ADZUNA_MAX_RESULTS_PER_PAGE = 50
ADZUNA_USER_AGENT = (
    "EU-Tech-Labour-Observatory/0.1 (+public job-data research, robots-and-ToS-compliant, "
    "Adzuna API terms of service)"
)
#: Free-tier documented limits (developer.adzuna.com/docs/terms_of_service):
#: 25 hits/min, 250 hits/day. 25/min => >= 2.4 s between requests; 2.5 s honors it.
ADZUNA_PACING_SECONDS = 2.5
#: Default sweep page budget. Two independent limits bind: the free tier's
#: 250 hits/day and Adzuna's per-query result window (probed live: pages beyond
#: ~100 return listings already seen on earlier pages, so one all-active query
#: yields at most ~5,000 unique rows). 100 pages (~5,000 rows, ~4.5 min) stays
#: inside both, leaving the rest of the daily quota for other countries.
ADZUNA_DEFAULT_PAGE_BUDGET = 100


def parse_adzuna_datetime(value: str | None) -> datetime | None:
    """Parse Adzuna's ISO-8601 timestamps (``2013-11-08T18:07:39Z``)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def adzuna_credentials() -> tuple[str, str]:
    """Load ``ADZUNA_APP_ID`` / ``ADZUNA_APP_KEY`` from env or ``.env``.

    Adzuna requires credentials for every request; keys are never hardcoded.
    Raises :class:`RuntimeError` (before any network call) when missing.
    """
    app_id = os.environ.get("ADZUNA_APP_ID") or read_dotenv_value("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY") or read_dotenv_value("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise RuntimeError(
            "ADZUNA_APP_ID and ADZUNA_APP_KEY are not set. Register free at "
            "https://developer.adzuna.com/signup and add both to .env. "
            "Keys must never be hardcoded."
        )
    return app_id, app_key


# ---------------------------------------------------------------------------
# Per-country configuration (the multi-country adapter)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CountryAdapter:
    """Configuration that makes one collector serve one Adzuna country domain.

    ``country_code`` is the URL path segment (``de``); ``expected_country`` is
    the ISO 3166-1 alpha-2 written to SAFE_FIELDS (``DE``); ``locale`` and
    ``language`` drive ``lang``/``source_language``. The scope parameters,
    source version, licence reference and coverage limitation travel with the
    adapter so a country sweep differs from any other only by this config.
    """

    country_code: str
    expected_country: str
    locale: str
    language: str
    source_version: str = ADZUNA_SOURCE_VERSION
    scope_id: str = "all-active"
    scope_params: Mapping[str, str] = field(default_factory=dict)
    licence_reference: str = "https://developer.adzuna.com/docs/terms_of_service"
    access_method: str = ADZUNA_ACCESS_METHOD
    freshness_threshold_hours: int = ADZUNA_FRESHNESS_THRESHOLD_HOURS
    coverage_limitations: str = ""


ADZUNA_DE_COVERAGE = (
    "Adzuna aggregates from source boards without per-source attribution; the "
    "same role can appear via different boards as distinct ads (dedupe is "
    "HMAC(source_id) only, cross-board merge impossible from the search "
    "payload). Free-tier API limits (25 hits/min, 250 hits/day) plus Adzuna's "
    "per-query result window (probed live: pages beyond ~100 repeat already "
    "seen listings) cap a single all-active sweep at ~5,000 rows (100 pages x "
    "50); the DE all-active stock advertises ~1.16M listings and is covered "
    "across consecutive sweeps. Region mapping not_present (location free text "
    "only, no NUTS codes); ESCO occupation mapping deferred. "
    "number_of_vacancies defaults to 1."
)

ADZUNA_NL_COVERAGE = (
    "Adzuna aggregates from source boards without per-source attribution; the "
    "same role can appear via different boards as distinct ads (dedupe is "
    "HMAC(source_id) only, cross-board merge impossible from the search "
    "payload). Free-tier API limits (25 hits/min, 250 hits/day) plus Adzuna's "
    "per-query result window (probed live: pages beyond ~100 repeat already "
    "seen listings) cap a single all-active sweep at ~5,000 rows (100 pages x "
    "50); the NL all-active stock advertises ~190k listings and is covered "
    "across consecutive sweeps. Region mapping not_present (location free text "
    "only, no NUTS codes); ESCO occupation mapping deferred. "
    "number_of_vacancies defaults to 1."
)

ADZUNA_DE = CountryAdapter(
    country_code="de",
    expected_country="DE",
    locale="de_DE",
    language="de",
    scope_id="de-all-active",
    scope_params={
        "source": "adzuna",
        "country": "DE",
        "query": "all-active",
        "locale": "de_DE",
    },
    coverage_limitations=ADZUNA_DE_COVERAGE,
)

ADZUNA_NL = CountryAdapter(
    country_code="nl",
    expected_country="NL",
    locale="nl_NL",
    language="nl",
    scope_id="nl-all-active",
    scope_params={
        "source": "adzuna",
        "country": "NL",
        "query": "all-active",
        "locale": "nl_NL",
    },
    coverage_limitations=ADZUNA_NL_COVERAGE,
)

#: Registry keyed by ``country_code``; main.py picks the adapter by country.
ADZUNA_ADAPTERS: dict[str, CountryAdapter] = {
    "de": ADZUNA_DE,
    "nl": ADZUNA_NL,
}


# ---------------------------------------------------------------------------
# Source-native payload models (extra="ignore": PII fields never enter parse)
# ---------------------------------------------------------------------------


class AdzunaLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    area: list[str] = Field(default_factory=list)
    display_name: str | None = None


class AdzunaCategory(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str | None = None
    tag: str | None = None


class AdzunaJob(BaseModel):
    """The allowlist-relevant slice of one search result.

    ``id`` is required so a schema drift fails loudly. ``title``, ``description``,
    ``company``, contacts and ``redirect_url`` are deliberately not declared:
    they never enter the parse step.
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    created: str | None = None
    category: AdzunaCategory | None = None
    location: AdzunaLocation | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _id_to_str(cls, value: object) -> object:
        # Probed live: DE returns string ids, NL returns integers.
        if isinstance(value, int):
            return str(value)
        return value


class AdzunaSearchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    count: int = 0
    results: list[AdzunaJob] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class AdzunaCollector(BaseCollector):
    """Collector for Adzuna's keyed job search API across country domains.

    Paginates ``/search/{page}`` for the adapter's country, optionally across
    category segments (to stretch past a per-query page cap), deduping on
    HMAC ``source_id`` so overlapping segments never double-write a listing.
    """

    source: ClassVar[str] = "adzuna"

    def __init__(
        self,
        *,
        scope_id: str,
        sweep_id: str,
        observed_at: datetime,
        hmac_key: bytes,
        adapter: CountryAdapter,
        app_id: str,
        app_key: str,
        results_per_page: int = ADZUNA_MAX_RESULTS_PER_PAGE,
        max_pages: int | None = None,
        segments: Sequence[Mapping[str, str]] = (),
        segment_by_category: bool = False,
        pacing_interval: float = ADZUNA_PACING_SECONDS,
        policy: RetryPolicy | None = None,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            scope_id=scope_id, sweep_id=sweep_id, observed_at=observed_at, timeout=timeout
        )
        if len(hmac_key) < 32:
            raise ValueError("hmac_key must be at least 32 bytes")
        if not app_id or not app_key:
            raise ValueError("Adzuna requires app_id and app_key for every request")
        self._hmac_key = hmac_key
        self._adapter = adapter
        self.expected_country = adapter.expected_country
        self._app_id = app_id
        self._app_key = app_key
        self._results_per_page = max(1, min(results_per_page, ADZUNA_MAX_RESULTS_PER_PAGE))
        self._max_pages = max_pages
        self._segments = list(segments)
        self._segment_by_category = segment_by_category
        self._policy = policy or RetryPolicy()
        self._pacer = PacingGate(min_interval=pacing_interval)
        self.total_elements = 0
        self.total_pages = 0
        self.completed_pages = 0
        #: The API's advertised total for the first (all-active) query, when seen.
        self.advertised_count: int | None = None
        self._headers = {"User-Agent": ADZUNA_USER_AGENT, "Accept": "application/json"}

    def _search_url(self, page: int) -> str:
        return f"{ADZUNA_API_BASE}/{self._adapter.country_code}/search/{page}"

    def _search_params(self, segment: Mapping[str, str]) -> dict[str, str]:
        params: dict[str, str] = {
            "app_id": self._app_id,
            "app_key": self._app_key,
            "results_per_page": str(self._results_per_page),
            "content-type": "application/json",
        }
        params.update(segment)
        return params

    async def _search(self, page: int, segment: Mapping[str, str]) -> AdzunaSearchResponse:
        async def do_get() -> httpx.Response:
            return await self._client.get(
                self._search_url(page), params=self._search_params(segment), headers=self._headers
            )

        await self._pacer.wait()
        response = await with_backoff(self._policy)(do_get)()
        if response.status_code != 200:
            response.raise_for_status()
        return AdzunaSearchResponse.model_validate(response.json())

    async def list_categories(self) -> list[str]:
        """Fetch the country's category tags (for category-segmented sweeps)."""
        url = f"{ADZUNA_API_BASE}/{self._adapter.country_code}/categories"

        async def do_get() -> httpx.Response:
            return await self._client.get(
                url,
                params={"app_id": self._app_id, "app_key": self._app_key},
                headers=self._headers,
            )

        await self._pacer.wait()
        response = await with_backoff(self._policy)(do_get)()
        if response.status_code != 200:
            response.raise_for_status()
        payload = response.json()
        return [
            str(item["tag"])
            for item in payload.get("results", [])
            if isinstance(item, dict) and item.get("tag")
        ]

    def fetch(self) -> AsyncIterator[RawRecord]:
        """Walk the paginated search API, yielding one RawRecord per ad."""
        return self._fetch()

    async def _fetch(self) -> AsyncIterator[RawRecord]:
        segments: list[Mapping[str, str]]
        if self._segments:
            segments = self._segments
        elif self._segment_by_category:
            segments = [{"category": tag} for tag in await self.list_categories()]
        else:
            segments = [{}]

        seen: set[str] = set()
        rows_seen = 0
        for segment in segments:
            page = 1
            while True:
                if self._max_pages is not None and self.completed_pages >= self._max_pages:
                    break
                result = await self._search(page, segment)
                self.completed_pages += 1
                if self.advertised_count is None:
                    self.advertised_count = result.count or None
                if not result.results:
                    break
                new_in_page = 0
                for job in result.results:
                    source_id = pseudonymize(job.id, self._hmac_key)
                    if source_id in seen:
                        continue
                    seen.add(source_id)
                    new_in_page += 1
                    rows_seen += 1
                    yield RawRecord(native_id=job.id, payload=job.model_dump())
                # Adzuna recycles its result window: a page with no new listings
                # means this query has nothing more to give (probed live).
                if new_in_page == 0:
                    break
                if self.advertised_count is not None and rows_seen >= self.advertised_count:
                    break
                if len(result.results) < self._results_per_page:
                    break
                page += 1
            if self._max_pages is not None and self.completed_pages >= self._max_pages:
                break

        # Manifest reconciliation: report what this sweep actually planned.
        self._finalize_totals(rows_seen, len(segments))

    def _finalize_totals(self, rows_seen: int, segment_count: int) -> None:
        """Compute expected_pages/expected_rows so the manifest reconciles.

        Single all-active query with an advertised ``count``: plan exactly the
        pages this sweep intended to fetch (bounded by the page budget) and the
        rows they should contain. Otherwise (segmented or count-less) report
        what was actually fetched so a clean run stays complete and any
        truncation surfaces as ``partial``.
        """
        if self.advertised_count is not None and segment_count == 1 and not self._segments:
            total = self.advertised_count
            planned_pages = math.ceil(total / self._results_per_page)
            if self._max_pages is not None:
                planned_pages = min(planned_pages, self._max_pages)
                self.total_pages = planned_pages
                # Budgeted sweep: the budget is the plan; report the rows the
                # budgeted pages actually yielded (live-feed dedupe applies).
                self.total_elements = rows_seen
            else:
                self.total_pages = planned_pages
                self.total_elements = min(total, planned_pages * self._results_per_page)
        else:
            self.total_pages = self.completed_pages
            self.total_elements = rows_seen

    def parse(self, raw: RawRecord) -> dict[str, Any]:
        """Extract the source-native fields the allowlist needs."""
        job = AdzunaJob(**raw.payload)
        return {
            "native_id": job.id,
            "first_published": parse_adzuna_datetime(job.created),
            "category_tag": job.category.tag if job.category else None,
        }

    def normalize(self, parsed: dict[str, Any]) -> NormalizedRecord:
        """Map parsed fields onto the SAFE_FIELDS allowlist and pseudonymize the id."""
        return NormalizedRecord(
            source=self.source,
            source_id=pseudonymize(parsed["native_id"], self._hmac_key),
            scope_id=self.scope_id,
            sweep_id=self.sweep_id,
            observed_at=self.observed_at,
            first_published=parsed["first_published"],
            last_modified=None,
            removed_at=None,
            nuts_code=None,
            nuts_label=None,
            region_mapping_status="not_present",
            region_mapping_method="adzuna_location_text_deferred",
            country=self._adapter.expected_country,
            esco_occupation_uri=None,
            esco_occupation_label=None,
            occupation_mapping_status="not_present",
            occupation_mapping_method="deferred_adzuna_category_to_esco",
            source_language=self._adapter.language,
            jobtech_taxonomy_version="",
            esco_version="1.2.1",
            skill_mappings=[],
            lang=self._adapter.language,
            number_of_vacancies=1,
        )
