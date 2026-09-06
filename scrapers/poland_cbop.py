"""Poland CBOP / ePraca collector — SCRAPER_ROADMAP.md Increment 1.

The public search JSON API of the Centralna Baza Ofert Pracy portal:

    POST https://oferty.praca.gov.pl/portal-api/v3/oferta/wyszukiwanie
    body  {"kodJezyka":"PL"}          (no auth, no cookies)
    query page=0&size=100&sort=stanowisko,asc

Spring Data pagination: ``payload.ofertyPracyPage`` carries ``totalElements``,
``totalPages``, ``last`` and ``content``. A full sweep walks pages 0..last.

Only the SAFE_FIELDS allowlist leaves this module; PII fields (email, phone,
contact person, employer, addresses) exist in the raw payload but are excluded
by ``NormalizedRecord(extra="forbid")``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, ConfigDict, Field

from scrapers.base import REQUEST_TIMEOUT_SECONDS, BaseCollector, NormalizedRecord, RawRecord
from scrapers.retry import RetryPolicy, with_backoff
from scrapers.robots import PacingGate
from scrapers.sanitize import pseudonymize

CBOP_BASE = "https://oferty.praca.gov.pl/portal-api/v3/oferta/wyszukiwanie"
CBOP_SOURCE_VERSION = "portal-api-v3"
CBOP_SCOPE_ID = "pl-all-active"
CBOP_SCOPE_PARAMS: dict[str, str] = {
    "source": "cbop",
    "country": "PL",
    "kodJezyka": "PL",
    "query": "all-active",
}
CBOP_LICENCE_REFERENCE = "https://creativecommons.org/licenses/by/3.0/pl/"
CBOP_ACCESS_METHOD = "public-api"
CBOP_FRESHNESS_THRESHOLD_HOURS = 24
CBOP_COVERAGE_LIMITATIONS = (
    "List search payload only; per-offer vacancy count not exposed "
    "(number_of_vacancies defaults to 1); NUTS/ESCO mapping not implemented."
)
CBOP_USER_AGENT = (
    "EU-Tech-Labour-Observatory/0.1 (+public job-data research, robots-and-ToS-compliant)"
)


class CbopOffer(BaseModel):
    """One offer from the search API — only the fields the allowlist needs."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    status: str = "A"  # "A" = active
    dataDodaniaCbop: str | None = None  # DD.MM.YYYY
    dataWaznOd: str | None = None  # DD.MM.YYYY
    dataWaznDo: str | None = None  # DD.MM.YYYY
    miejscowoscId: str | None = None
    miejscowoscNazwa: str | None = None
    typOfertyEnum: str | None = None
    liczbaWolnychMiejscDlaNiepeln: int | None = None


class CbopPage(BaseModel):
    """Spring Data page envelope (extra fields such as ``sort`` ignored)."""

    model_config = ConfigDict(extra="ignore")

    number: int
    totalElements: int
    totalPages: int
    last: bool
    content: list[CbopOffer] = Field(default_factory=list)


class CbopPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ofertyPracyPage: CbopPage
    iloscMiejscPracy: int = 0


class CbopResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: int
    msg: str = ""
    payload: CbopPayload


def parse_pl_date(value: str | None) -> datetime | None:
    """Parse CBOP's ``DD.MM.YYYY`` dates as UTC midnights; garbage becomes None."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d.%m.%Y").replace(tzinfo=UTC)
    except ValueError:
        return None


class PolandCollector(BaseCollector):
    """Collector for CBOP/ePraca (Poland); ``CBOPCollector`` is the roadmap alias."""

    source: ClassVar[str] = "cbop"
    country: ClassVar[str] = "PL"

    def __init__(
        self,
        *,
        scope_id: str,
        sweep_id: str,
        observed_at: datetime,
        hmac_key: bytes,
        page_size: int = 100,
        max_pages: int | None = None,
        pacing_interval: float = 1.0,
        policy: RetryPolicy | None = None,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            scope_id=scope_id, sweep_id=sweep_id, observed_at=observed_at, timeout=timeout
        )
        if len(hmac_key) < 32:
            raise ValueError("hmac_key must be at least 32 bytes")
        self._hmac_key = hmac_key
        self._page_size = page_size
        self._max_pages = max_pages
        self._policy = policy or RetryPolicy()
        self._pacer = PacingGate(min_interval=pacing_interval)
        self.total_elements = 0
        self.total_pages = 0
        self.completed_pages = 0
        self._headers = {"User-Agent": CBOP_USER_AGENT, "Accept": "application/json"}

    async def _search(self, page: int) -> CbopResponse:
        async def do_search(page: int) -> httpx.Response:
            return await self._client.post(
                CBOP_BASE,
                params={"page": page, "size": self._page_size, "sort": "stanowisko,asc"},
                json={"kodJezyka": "PL"},
                headers=self._headers,
            )

        await self._pacer.wait()
        response = await with_backoff(self._policy)(do_search)(page)
        if response.status_code != 200:
            response.raise_for_status()
        return CbopResponse.model_validate(response.json())

    def fetch(self) -> AsyncIterator[RawRecord]:
        """Walk the paginated search API, yielding one RawRecord per offer."""
        return self._fetch()

    async def _fetch(self) -> AsyncIterator[RawRecord]:
        page = 0
        while True:
            if self._max_pages is not None and page >= self._max_pages:
                break
            result = await self._search(page)
            page_info = result.payload.ofertyPracyPage
            self.total_elements = page_info.totalElements
            self.total_pages = page_info.totalPages
            self.completed_pages += 1
            for offer in page_info.content:
                yield RawRecord(native_id=offer.id, payload=offer.model_dump())
            if page_info.last or not page_info.content:
                break
            page += 1

    def parse(self, raw: RawRecord) -> dict[str, Any]:
        """Extract the source-native fields the allowlist needs."""
        offer = CbopOffer(**raw.payload)
        return {
            "native_id": offer.id,
            "first_published": parse_pl_date(offer.dataDodaniaCbop),
            "last_modified": parse_pl_date(offer.dataWaznOd),
            "removed_at": None if offer.status == "A" else self.observed_at,
            "number_of_vacancies": 1,
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
            last_modified=parsed["last_modified"],
            removed_at=parsed["removed_at"],
            country=self.country,
            source_language="pl",
            lang="pl",
            number_of_vacancies=parsed["number_of_vacancies"],
        )


#: Roadmap deliverable naming (``scrapers/poland_cbop.py`` / ``CBOPCollector``).
CBOPCollector = PolandCollector
