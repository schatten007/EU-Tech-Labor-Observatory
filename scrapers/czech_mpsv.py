"""Czech Úřad práce / MPSV collector — SCRAPER_ROADMAP.md Increment 2.

The national open-data active-set dump of vacancies registered with the Czech
labour office (Úřad práce ČR):

    GET https://data.mpsv.cz/od/soubory/volna-mista/volna-mista.json
    body  none (no auth, no cookies)
    shape {"polozky": [...]}              -- full dump, no pagination

Refreshed daily ("Opendatová sada 1x denně"). One request per sweep; the dump
is ~186 MB / ~39k active vacancies.

Region mapping uses MPSV's own codelists (pinned in ``data/reference/``): the
kraje codelist carries ``kodNuts3`` (CZ010-CZ080, unchanged in NUTS 2024), and
okresy/obce resolve to a kraj through the same chain. Only the SAFE_FIELDS
allowlist leaves this module; contact names, emails, telephones, addresses,
employer data and free text exist in the raw payload but are excluded by
``NormalizedRecord(extra="forbid")``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, ConfigDict

from scrapers.base import (
    BaseCollector,
    MappingStatus,
    NormalizedRecord,
    RawRecord,
)
from scrapers.retry import RetryPolicy, with_backoff
from scrapers.robots import PacingGate
from scrapers.sanitize import pseudonymize

MPSV_DUMP_URL = "https://data.mpsv.cz/od/soubory/volna-mista/volna-mista.json"
MPSV_SOURCE_VERSION = "volna-mista-json-v1"
MPSV_SCOPE_ID = "cz-all-active"
MPSV_SCOPE_PARAMS: dict[str, str] = {
    "source": "mpsv",
    "country": "CZ",
    "dataset": "volna-mista-za-celou-cr",
    "format": "json",
}
MPSV_LICENCE_REFERENCE = "https://data.mpsv.cz/web/data/podminky-uziti"
MPSV_ACCESS_METHOD = "public-api"
MPSV_FRESHNESS_THRESHOLD_HOURS = 24
MPSV_COVERAGE_LIMITATIONS = (
    "Active-set daily dump of vacancies published on JPŘ PSV (MPSV open data); "
    "single full-dump GET, no pagination. Region resolved via MPSV codelists "
    "(kraj -> NUTS 2024, okres/obec fallback chain); workplace region covers "
    "~91% of records, remainder via contact address (low_confidence) or "
    "district/municipality. ESCO occupation/skill mapping deferred "
    "(occupation_mapping_status=not_present). Removed postings leave the dump; "
    "removed_at is stamped by the reconciliation step (scrapers.reconcile_mpsv)."
)
MPSV_USER_AGENT = (
    "EU-Tech-Labour-Observatory/0.1 (+public job-data research, robots-and-ToS-compliant)"
)
#: The full dump is ~186 MB; give the single daily request room to complete.
MPSV_DOWNLOAD_TIMEOUT = 300.0

REFERENCE_FILES = (
    "mpsv_kraje_nuts_2024.csv",
    "mpsv_okresy_kraj_2024.csv",
    "mpsv_obce_kraj_2024.csv",
)


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def parse_cz_datetime(value: str | None) -> datetime | None:
    """Parse MPSV's ISO-8601 timestamps (``2026-02-18T00:00:00.000Z``)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_cz_date(value: str | None) -> datetime | None:
    """Parse MPSV's date-only fields (``2026-09-01``) as UTC midnights."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Source-native payload models (extra="ignore": PII fields never enter parse)
# ---------------------------------------------------------------------------


class MpsvRef(BaseModel):
    """A codelist reference, e.g. ``{"id": "Kraj/132"}``."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None


class MpsvAdresa(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kraj: MpsvRef | None = None


class MpsvPracoviste(BaseModel):
    model_config = ConfigDict(extra="ignore")

    adresa: MpsvAdresa | None = None


class MpsvMistoVykonuPrace(BaseModel):
    model_config = ConfigDict(extra="ignore")

    obec: MpsvRef | None = None
    okresy: list[MpsvRef] | None = None
    pracoviste: list[MpsvPracoviste] | None = None


class MpsvKdeSeHlasit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    adresa: MpsvAdresa | None = None


class MpsvPrvniKontakt(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kdeSeHlasit: MpsvKdeSeHlasit | None = None


class MpsvOffer(BaseModel):
    """The allowlist-relevant slice of one dump record.

    ``portalId``, ``datumVlozeni``, ``datumZmeny`` and ``pocetMist`` are
    required so a schema drift fails loudly instead of silently dropping rows.
    """

    model_config = ConfigDict(extra="ignore")

    portalId: int
    datumVlozeni: str
    datumZmeny: str
    expirace: str | None = None
    pocetMist: int
    mistoVykonuPrace: MpsvMistoVykonuPrace | None = None
    prvniKontaktSeZamestnavatelem: MpsvPrvniKontakt | None = None


# ---------------------------------------------------------------------------
# Region crosswalk (NUTS 2024)
# ---------------------------------------------------------------------------


class RegionResolution(BaseModel):
    """Outcome of the codelist -> NUTS 2024 resolution for one record."""

    nuts_code: str | None = None
    nuts_label: str | None = None
    status: MappingStatus = "unmapped"
    method: str = "not_available"


class MpsvCrosswalk:
    """Loads the pinned ``data/reference/mpsv_*.csv`` tables and resolves regions.

    Matching rules (first hit wins), per the Increment 2 plan §2:

    1. workplace region (``mistoVykonuPrace.pracoviste[].adresa.kraj``) -> mapped
       (ambiguous when workplaces disagree)
    2. contact-address region (``prvniKontaktSeZamestnavatelem.kdeSeHlasit``)
       -> low_confidence (contact may differ from the workplace)
    3. districts (``mistoVykonuPrace.okresy``) -> mapped / ambiguous
    4. municipality (``mistoVykonuPrace.obec``) -> mapped
    5. otherwise -> unmapped
    """

    def __init__(self, reference_dir: Path) -> None:
        self._mapping: dict[str, tuple[str, str]] = {}
        for name in REFERENCE_FILES:
            path = reference_dir / name
            if not path.exists():
                raise FileNotFoundError(f"missing MPSV crosswalk reference: {path}")
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    self._mapping[row["source_code"]] = (row["nuts_code"], row["nuts_label"])

    def _regions(self, codes: Sequence[str]) -> list[tuple[str, str]]:
        seen: dict[str, tuple[str, str]] = {}
        for code in codes:
            hit = self._mapping.get(code)
            if hit is not None:
                seen[hit[0]] = hit
        return list(seen.values())

    def resolve(
        self,
        *,
        work_kraje: Sequence[str] = (),
        contact_kraj: str | None = None,
        okres_ids: Sequence[str] = (),
        obec_id: str | None = None,
    ) -> RegionResolution:
        regions = self._regions(work_kraje)
        if regions:
            code, label = regions[0]
            return RegionResolution(
                nuts_code=code,
                nuts_label=label,
                status="ambiguous" if len(regions) > 1 else "mapped",
                method="mpsv_kraje_codelist_nuts3",
            )
        if contact_kraj is not None:
            hit = self._mapping.get(contact_kraj)
            if hit is not None:
                return RegionResolution(
                    nuts_code=hit[0],
                    nuts_label=hit[1],
                    status="low_confidence",
                    method="mpsv_kraje_codelist_contact_address",
                )
        regions = self._regions(okres_ids)
        if regions:
            code, label = regions[0]
            return RegionResolution(
                nuts_code=code,
                nuts_label=label,
                status="ambiguous" if len(regions) > 1 else "mapped",
                method="mpsv_okres_codelist_nuts3",
            )
        if obec_id is not None:
            hit = self._mapping.get(obec_id)
            if hit is not None:
                return RegionResolution(
                    nuts_code=hit[0],
                    nuts_label=hit[1],
                    status="mapped",
                    method="mpsv_obec_codelist_nuts3",
                )
        return RegionResolution(method="not_available")


def crosswalk_reference_hashes(reference_dir: Path) -> str:
    """SHA-256 of the three crosswalk CSVs (content only), sorted by filename."""
    parts: list[str] = []
    for name in sorted(REFERENCE_FILES):
        digest = hashlib.sha256()
        with (reference_dir / name).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        parts.append(f"{name}:{digest.hexdigest()}")
    return ";".join(parts)


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class MPSVCollector(BaseCollector):
    """Collector for the MPSV daily active-set dump (Czechia)."""

    source: ClassVar[str] = "mpsv"
    country: ClassVar[str] = "CZ"

    def __init__(
        self,
        *,
        scope_id: str,
        sweep_id: str,
        observed_at: datetime,
        hmac_key: bytes,
        reference_dir: Path = Path("data/reference"),
        pacing_interval: float = 1.0,
        policy: RetryPolicy | None = None,
        timeout: float = MPSV_DOWNLOAD_TIMEOUT,
    ) -> None:
        super().__init__(
            scope_id=scope_id, sweep_id=sweep_id, observed_at=observed_at, timeout=timeout
        )
        if len(hmac_key) < 32:
            raise ValueError("hmac_key must be at least 32 bytes")
        self._hmac_key = hmac_key
        self._crosswalk = MpsvCrosswalk(reference_dir)
        self._policy = policy or RetryPolicy()
        self._pacer = PacingGate(min_interval=pacing_interval)
        self._headers = {"User-Agent": MPSV_USER_AGENT, "Accept": "application/json"}
        self.total_elements = 0
        self.total_pages = 1
        self.completed_pages = 0
        #: HMAC source_id -> expirace (date-only, UTC), for the reconciliation step.
        self.expirace_by_source_id: dict[str, str] = {}

    async def _download(self, tmp: Path) -> httpx.Response:
        async def do_get() -> httpx.Response:
            request = self._client.build_request("GET", MPSV_DUMP_URL, headers=self._headers)
            response = await self._client.send(request, stream=True)
            if response.status_code != 200:
                await response.aclose()
                return response
            with tmp.open("wb") as handle:
                async for chunk in response.aiter_bytes(1 << 20):
                    handle.write(chunk)
            await response.aclose()
            return response

        await self._pacer.wait()
        response = await with_backoff(self._policy)(do_get)()
        if response.status_code != 200:
            raise httpx.HTTPStatusError(
                f"MPSV dump returned HTTP {response.status_code}",
                request=response.request,
                response=response,
            )
        return response

    def fetch(self) -> AsyncIterator[RawRecord]:
        """Download the full dump once and yield one RawRecord per vacancy."""
        return self._fetch()

    async def _fetch(self) -> AsyncIterator[RawRecord]:
        tmp = Path(tempfile.gettempdir()) / f"mpsv_vm_{self.sweep_id}_{uuid.uuid4().hex}.json"
        try:
            await self._download(tmp)
            with tmp.open(encoding="utf-8") as handle:
                data: Mapping[str, Any] = json.load(handle)
            items = list(data.get("polozky", []))
            self.total_elements = len(items)
            self.total_pages = 1
            self.completed_pages = 1
            for item in items:
                portal_id = item.get("portalId")
                if portal_id is None:
                    raise ValueError("MPSV record missing portalId")
                yield RawRecord(native_id=str(portal_id), payload=item)
        finally:
            tmp.unlink(missing_ok=True)

    def parse(self, raw: RawRecord) -> dict[str, Any]:
        """Extract the source-native fields the allowlist needs."""
        offer = MpsvOffer.model_validate(raw.payload)
        mvp = offer.mistoVykonuPrace
        work_kraje: list[str] = []
        okres_ids: list[str] = []
        obec_id: str | None = None
        if mvp is not None:
            for pracoviste in mvp.pracoviste or []:
                kraj = pracoviste.adresa.kraj if pracoviste.adresa else None
                if kraj is not None and kraj.id:
                    work_kraje.append(kraj.id)
            for okres in mvp.okresy or []:
                if okres.id:
                    okres_ids.append(okres.id)
            if mvp.obec is not None and mvp.obec.id:
                obec_id = mvp.obec.id
        contact_kraj: str | None = None
        if offer.prvniKontaktSeZamestnavatelem is not None:
            kde = offer.prvniKontaktSeZamestnavatelem.kdeSeHlasit
            if kde is not None and kde.adresa is not None and kde.adresa.kraj is not None:
                contact_kraj = kde.adresa.kraj.id
        return {
            "native_id": str(offer.portalId),
            "first_published": parse_cz_datetime(offer.datumVlozeni),
            "last_modified": parse_cz_datetime(offer.datumZmeny),
            "expirace": parse_cz_date(offer.expirace),
            "number_of_vacancies": offer.pocetMist,
            "work_kraje": work_kraje,
            "contact_kraj": contact_kraj,
            "okres_ids": okres_ids,
            "obec_id": obec_id,
        }

    def normalize(self, parsed: dict[str, Any]) -> NormalizedRecord:
        """Map parsed fields onto the SAFE_FIELDS allowlist and pseudonymize the id."""
        region = self._crosswalk.resolve(
            work_kraje=parsed["work_kraje"],
            contact_kraj=parsed["contact_kraj"],
            okres_ids=parsed["okres_ids"],
            obec_id=parsed["obec_id"],
        )
        source_id = pseudonymize(parsed["native_id"], self._hmac_key)
        expirace = parsed["expirace"]
        if expirace is not None:
            self.expirace_by_source_id[source_id] = expirace.strftime("%Y-%m-%d")
        return NormalizedRecord(
            source=self.source,
            source_id=source_id,
            scope_id=self.scope_id,
            sweep_id=self.sweep_id,
            observed_at=self.observed_at,
            first_published=parsed["first_published"],
            last_modified=parsed["last_modified"],
            removed_at=None,
            nuts_code=region.nuts_code,
            nuts_label=region.nuts_label,
            region_mapping_status=region.status,
            region_mapping_method=region.method,
            country=self.country,
            occupation_mapping_status="not_present",
            occupation_mapping_method="deferred_cz_isco_to_esco",
            source_language="cs",
            lang="cs",
            number_of_vacancies=parsed["number_of_vacancies"],
        )
