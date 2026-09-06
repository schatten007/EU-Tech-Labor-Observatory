"""France Travail collector — SCRAPER_ROADMAP.md Increment 4.

Official REST API "Offres d'emploi v2" of the French public employment service
(ex-Pôle emploi), the real-time base of active offers collected by France Travail
and its consenting partners:

    POST https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire
         grant_type=client_credentials&client_id=...&client_secret=...
         &scope=api_offresdemploiv2 o2dsoffre          -> {access_token, expires_in: 1499, ...}

    GET  https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search?range=0-149
         Authorization: Bearer <access_token>          -> 206 + Content-Range: offres 0-149/503356

Contract pinned live on 2026-08-22:

- **Auth.** OAuth2 client-credentials, opaque bearer token, ``expires_in`` 1499 s
  (~25 min). An expired/invalid token answers **401 with an empty body** and
  ``WWW-Authenticate: Bearer``; the collector refreshes once and replays the
  request. Tokens are minted lazily and reused until ``expires_in`` minus a
  safety skew, so a long sweep never hammers the token endpoint.
- **Pagination.** ``range=<start>-<end>`` (not a Range header), answered with
  ``206 Partial Content`` plus ``Content-Range: offres <start>-<end>/<total>``
  and ``accept-range: 150``. A window wider than 150 items is rejected
  (``400 "La plage de résultats demandée est trop importante."``) and a start
  position above 3000 is rejected (``400 "La position de début doit être
  inférieure ou égale à 3000."``) — so **one query yields at most 3,150 offers**
  (21 windows), while the national active stock is ~503k.
- **Segmentation.** The sweep therefore runs one query per **département**
  (``departement=<code>``, 101 codes from the pinned crosswalk) on top of one
  unsegmented query that records the national advertised total. Offers are
  deduped on their HMAC ``source_id`` across segments.
- **Rate limits.** Response headers expose a per-client-id limiter of 10 req/s
  (``x-ratelimit-replenish-rate-clientidlimiter: 10``), matching the documented
  "10 appels / seconde". The collector paces at the charter floor of >= 1 s and
  honors ``Retry-After`` on 429 through ``scrapers.retry``.

SAFE_FIELDS mapping:

- ``source_id``        = HMAC of the native offer ``id`` (7-character FT id).
- ``first_published``  = ``dateCreation``; ``last_modified`` = ``dateActualisation``
  (both ISO 8601 with milliseconds, 100% populated in the live sample).
- ``number_of_vacancies`` = ``nombrePostes`` (100% populated live).
- **Region:** ``lieuTravail`` carries no NUTS code, so the département is derived
  and mapped through the pinned crosswalk (``data/reference/
  francetravail_departements_nuts_2024.csv``, 101 rows, département -> NUTS 3
  2024): ``commune`` INSEE code -> ``mapped``, ``codePostal`` -> ``low_confidence``
  (Corsican 20xxx postcodes cannot separate 2A/2B -> ``ambiguous``), the
  ``libelle`` département prefix -> ``low_confidence``, otherwise ``unmapped``
  (region-only or foreign locations such as "Île-de-France" or "Monaco").
- **Occupation:** ``romeCode`` is present on every offer but no pinned
  ROME -> ESCO 1.2.1 crosswalk exists yet, so the status is ``unmapped`` (not
  ``not_present`` as in Increments 1-3, where the source exposed no occupation
  code at all) with method ``deferred_rome_to_esco``.
- ``removed_at`` is not exposed; closures are absence-based across sweeps.

PII and licence compliance: the raw payload carries ``description``, ``intitule``,
``entreprise``, ``contact``, ``origineOffre`` (URLs), ``agence``, ``salaire`` and
``lieuTravail.libelle``/``codePostal``/``commune``. None of them are declared on
the payload models or written to disk — the allowlist-only parse plus
``NormalizedRecord(extra="forbid")`` is the enforcement point. This also
satisfies Article 7 of the Licence Offres d'emploi, which requires a derived
database to drop employer name/description/URL, contact name and phone numbers,
offer URLs and the **postcode, INSEE code and label of the workplace commune**:
those identifiers are used transiently to derive the NUTS 3 region and never
persisted.
"""

from __future__ import annotations

import csv
import hashlib
import math
import os
import re
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, ConfigDict, Field

from scrapers.base import (
    REQUEST_TIMEOUT_SECONDS,
    BaseCollector,
    MappingStatus,
    NormalizedRecord,
    RawRecord,
)
from scrapers.retry import RetryPolicy, with_backoff
from scrapers.robots import PacingGate
from scrapers.sanitize import pseudonymize, read_dotenv_value

FT_TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
FT_TOKEN_REALM = "/partenaire"
FT_SCOPE = "api_offresdemploiv2 o2dsoffre"
FT_API_BASE = "https://api.francetravail.io/partenaire/offresdemploi/v2"
FT_SEARCH_URL = f"{FT_API_BASE}/offres/search"

FT_SOURCE_VERSION = "offresdemploi-v2"
FT_SCOPE_ID = "fr-all-active"
FT_SCOPE_PARAMS: dict[str, str] = {
    "source": "francetravail",
    "country": "FR",
    "api": "offresdemploi-v2",
    "query": "all-active",
    "segmentation": "departement",
}
FT_LICENCE_REFERENCE = (
    "https://francetravail.io/produits-partages/documentation/"
    "conditions-dutilisation-api/licence-offres-emploi"
)
FT_ACCESS_METHOD = "public-api"
#: Licence Offres d'emploi article 5.2 requires the API to be solicited at least
#: once every 24 hours.
FT_FRESHNESS_THRESHOLD_HOURS = 24

#: ``accept-range: 150`` — a wider window is rejected with HTTP 400.
FT_MAX_WINDOW = 150
#: "La position de début doit être inférieure ou égale à 3000" (probed live).
FT_MAX_START = 3000
#: Documented limit is 10 req/s per client id; the charter floor of 1 s applies.
FT_PACING_SECONDS = 1.0
#: Refresh the token this many seconds before ``expires_in`` elapses.
FT_TOKEN_SKEW_SECONDS = 60.0
#: Fallback lifetime when the token endpoint omits ``expires_in``.
FT_TOKEN_DEFAULT_TTL = 1499

FT_USER_AGENT = (
    "EU-Tech-Labour-Observatory/0.1 (+public job-data research, robots-and-ToS-compliant, "
    "France Travail Licence Offres d'emploi)"
)

FT_REFERENCE_FILE = "francetravail_departements_nuts_2024.csv"

FT_COVERAGE_LIMITATIONS = (
    "Real-time API of active offers collected by France Travail and by partners "
    "that consented to API redistribution (partners without consent are absent). "
    "One query returns at most 3,150 offers (window <= 150 items, start position "
    "<= 3000, both probed live), so the sweep segments by département (101 codes) "
    "plus one unsegmented query that records the national advertised total; "
    "offers are deduped on HMAC source_id across segments. Offers whose "
    "lieuTravail carries no département (region-only, e.g. 'Île-de-France', or "
    "foreign locations) are only reachable through the unsegmented query and stay "
    "region-unmapped. Region derived from the pinned département -> NUTS 2024 "
    "crosswalk (commune INSEE = mapped, codePostal = low_confidence, Corsican "
    "20xxx = ambiguous, libellé prefix = low_confidence); ROME occupation code is "
    "present on every offer but ROME -> ESCO 1.2.1 mapping is deferred "
    "(occupation_mapping_status=unmapped). removed_at is not exposed by the API; "
    "closures are absence-based across consecutive sweeps."
)

#: ``lieuTravail.libelle`` is formatted ``"<département> - <commune>"``
#: (e.g. ``64 - Bayonne``, ``2A - AJACCIO``, ``971 - LE GOSIER``, ``30 - Gard``).
_LIBELLE_DEPARTEMENT = re.compile(r"^\s*(9[0-9]{2}|2[AB]|[0-9]{2})\s*-")

#: Overseas départements carry a three-character code (``971``..``976``).
_OVERSEAS_PREFIXES = ("97", "98")


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def france_travail_credentials() -> tuple[str, str]:
    """Load ``FRANCE_TRAVAIL_CLIENT_ID`` / ``_CLIENT_SECRET`` from env or ``.env``.

    Every API request needs an OAuth2 bearer token minted from these values;
    they are never hardcoded. Raises :class:`RuntimeError` before any network
    call when either is missing.
    """
    client_id = os.environ.get("FRANCE_TRAVAIL_CLIENT_ID") or read_dotenv_value(
        "FRANCE_TRAVAIL_CLIENT_ID"
    )
    client_secret = os.environ.get("FRANCE_TRAVAIL_CLIENT_SECRET") or read_dotenv_value(
        "FRANCE_TRAVAIL_CLIENT_SECRET"
    )
    if not client_id or not client_secret:
        raise RuntimeError(
            "FRANCE_TRAVAIL_CLIENT_ID and FRANCE_TRAVAIL_CLIENT_SECRET are not set. "
            "Create an application on https://francetravail.io, subscribe it to "
            "'Offres d'emploi v2', accept the Licence Offres d'emploi and add both "
            "values to .env. Credentials must never be hardcoded."
        )
    return client_id, client_secret


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def parse_ft_datetime(value: str | None) -> datetime | None:
    """Parse France Travail timestamps (``2026-08-22T18:04:03.871Z``)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Source-native payload models (extra="ignore": PII fields never enter parse)
# ---------------------------------------------------------------------------


class FTLieuTravail(BaseModel):
    """Workplace location.

    ``libelle``, ``codePostal`` and ``commune`` are read only to derive the
    département; Article 7 of the licence forbids persisting them, and the
    SAFE_FIELDS allowlist never carries them.
    """

    model_config = ConfigDict(extra="ignore")

    libelle: str | None = None
    codePostal: str | None = None
    commune: str | None = None


class FTOffre(BaseModel):
    """The allowlist-relevant slice of one search result.

    ``id`` is required so a schema drift fails loudly. ``intitule``,
    ``description``, ``entreprise``, ``contact``, ``origineOffre``, ``agence``
    and ``salaire`` are deliberately not declared: they never enter the parse
    step.
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    dateCreation: str | None = None
    dateActualisation: str | None = None
    nombrePostes: int | None = None
    romeCode: str | None = None
    lieuTravail: FTLieuTravail | None = None


class FTSearchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    resultats: list[FTOffre] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Region crosswalk (NUTS 2024)
# ---------------------------------------------------------------------------


class RegionResolution(BaseModel):
    """Outcome of the département -> NUTS 2024 resolution for one offer."""

    nuts_code: str | None = None
    nuts_label: str | None = None
    status: MappingStatus = "unmapped"
    method: str = "not_available"


def departement_from_commune(commune: str | None) -> str | None:
    """Département code from an INSEE commune code (``64102`` -> ``64``).

    Corsican communes carry a ``2A``/``2B`` prefix and overseas communes a
    three-digit prefix (``97113`` -> ``971``).
    """
    if not commune:
        return None
    code = commune.strip().upper()
    if len(code) < 2:
        return None
    if code[:2] in ("2A", "2B"):
        return code[:2]
    if code[:2] in _OVERSEAS_PREFIXES:
        return code[:3] if len(code) >= 3 else None
    return code[:2] if code[:2].isdigit() else None


def departement_from_code_postal(code_postal: str | None) -> tuple[str | None, bool]:
    """Département code from a postcode, plus whether Corsica made it ambiguous.

    Postcodes only approximate départements (a commune may use a neighbouring
    département's postcode), so the caller records ``low_confidence``. Corsican
    ``20xxx`` postcodes span both 2A and 2B and cannot be resolved.
    """
    if not code_postal:
        return None, False
    code = code_postal.strip()
    if len(code) < 2 or not code.isdigit():
        return None, False
    if code[:2] == "20":
        return None, True
    if code[:2] in _OVERSEAS_PREFIXES:
        return code[:3] if len(code) >= 3 else None, False
    return code[:2], False


def departement_from_libelle(libelle: str | None) -> str | None:
    """Département code from the ``"<département> - <commune>"`` label prefix."""
    if not libelle:
        return None
    match = _LIBELLE_DEPARTEMENT.match(libelle)
    return match.group(1).upper() if match else None


class FranceTravailCrosswalk:
    """Loads the pinned département -> NUTS 2024 table and resolves regions.

    Matching rules, first hit wins:

    1. ``lieuTravail.commune`` (INSEE code) -> ``mapped``
    2. ``lieuTravail.codePostal`` -> ``low_confidence`` (``20xxx`` -> ``ambiguous``)
    3. ``lieuTravail.libelle`` département prefix -> ``low_confidence``
    4. otherwise -> ``unmapped``
    """

    def __init__(self, reference_dir: Path) -> None:
        path = reference_dir / FT_REFERENCE_FILE
        if not path.exists():
            raise FileNotFoundError(
                f"missing France Travail crosswalk reference: {path} "
                "(rebuild with `python -m scrapers.reference_francetravail`)"
            )
        self._mapping: dict[str, tuple[str, str]] = {}
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                self._mapping[row["source_code"].strip().upper()] = (
                    row["nuts_code"],
                    row["nuts_label"],
                )
        if not self._mapping:
            raise ValueError(f"France Travail crosswalk reference is empty: {path}")

    def departements(self) -> list[str]:
        """The département codes the sweep segments by (sorted, stable)."""
        return sorted(self._mapping)

    def resolve(
        self,
        *,
        commune: str | None = None,
        code_postal: str | None = None,
        libelle: str | None = None,
    ) -> RegionResolution:
        hit = self._mapping.get(departement_from_commune(commune) or "")
        if hit is not None:
            return RegionResolution(
                nuts_code=hit[0],
                nuts_label=hit[1],
                status="mapped",
                method="ft_commune_insee_departement_nuts3",
            )
        postal_code, corsica_ambiguous = departement_from_code_postal(code_postal)
        if corsica_ambiguous:
            return RegionResolution(status="ambiguous", method="ft_code_postal_corse_2a_2b")
        hit = self._mapping.get(postal_code or "")
        if hit is not None:
            return RegionResolution(
                nuts_code=hit[0],
                nuts_label=hit[1],
                status="low_confidence",
                method="ft_code_postal_departement_nuts3",
            )
        hit = self._mapping.get(departement_from_libelle(libelle) or "")
        if hit is not None:
            return RegionResolution(
                nuts_code=hit[0],
                nuts_label=hit[1],
                status="low_confidence",
                method="ft_lieu_libelle_departement_nuts3",
            )
        return RegionResolution(method="not_available")


def crosswalk_reference_hashes(reference_dir: Path) -> str:
    """SHA-256 of the pinned crosswalk CSV (content only)."""
    digest = hashlib.sha256()
    with (reference_dir / FT_REFERENCE_FILE).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return f"{FT_REFERENCE_FILE}:{digest.hexdigest()}"


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

#: ``Content-Range: offres 0-149/503356``
_CONTENT_RANGE = re.compile(r"^\s*offres\s+(\d+)-(\d+)/(\d+)\s*$")


def parse_content_range(value: str | None) -> int | None:
    """Total advertised by ``Content-Range``, or None when absent/malformed."""
    if not value:
        return None
    match = _CONTENT_RANGE.match(value)
    return int(match.group(3)) if match else None


class FranceTravailCollector(BaseCollector):
    """Collector for the France Travail "Offres d'emploi v2" API (France).

    Mints an OAuth2 client-credentials token, honors its TTL, refreshes once on
    a 401, and walks ``range`` windows per département segment inside the API's
    150-item / 3000-start limits.
    """

    source: ClassVar[str] = "francetravail"
    country: ClassVar[str] = "FR"

    def __init__(
        self,
        *,
        scope_id: str,
        sweep_id: str,
        observed_at: datetime,
        hmac_key: bytes,
        client_id: str,
        client_secret: str,
        reference_dir: Path = Path("data/reference"),
        window: int = FT_MAX_WINDOW,
        max_pages: int | None = None,
        segments: Sequence[Mapping[str, str]] | None = None,
        pacing_interval: float = FT_PACING_SECONDS,
        policy: RetryPolicy | None = None,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(
            scope_id=scope_id, sweep_id=sweep_id, observed_at=observed_at, timeout=timeout
        )
        if len(hmac_key) < 32:
            raise ValueError("hmac_key must be at least 32 bytes")
        if not client_id or not client_secret:
            raise ValueError("France Travail requires client_id and client_secret for every token")
        self._hmac_key = hmac_key
        self._client_id = client_id
        self._client_secret = client_secret
        self._crosswalk = FranceTravailCrosswalk(reference_dir)
        self._window = max(1, min(window, FT_MAX_WINDOW))
        self._max_pages = max_pages
        self._segments = list(segments) if segments is not None else None
        self._policy = policy or RetryPolicy()
        self._pacer = PacingGate(min_interval=pacing_interval)
        self._monotonic = monotonic
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._headers = {"User-Agent": FT_USER_AGENT, "Accept": "application/json"}
        self.total_elements = 0
        self.total_pages = 0
        self.completed_pages = 0
        #: Token endpoint calls made by this sweep (TTL reuse keeps this small).
        self.token_requests = 0
        #: National active stock advertised by the unsegmented query, when seen.
        self.advertised_count: int | None = None
        #: Windows the advertised totals implied for the segments visited.
        self.planned_pages = 0

    # -- auth ---------------------------------------------------------------

    async def _mint_token(self) -> str:
        """Mint a client-credentials token (paced and retried like any call)."""

        async def do_post() -> httpx.Response:
            return await self._client.post(
                FT_TOKEN_URL,
                params={"realm": FT_TOKEN_REALM},
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": FT_SCOPE,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": FT_USER_AGENT,
                },
            )

        await self._pacer.wait()
        response = await with_backoff(self._policy)(do_post)()
        self.token_requests += 1
        if response.status_code != 200:
            response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("France Travail token endpoint returned no access_token")
        ttl = payload.get("expires_in")
        lifetime = float(ttl) if isinstance(ttl, int | float) and ttl else FT_TOKEN_DEFAULT_TTL
        self._token = token
        self._token_expires_at = self._monotonic() + max(1.0, lifetime - FT_TOKEN_SKEW_SECONDS)
        self._log.info("ft_token_minted", expires_in=lifetime, token_requests=self.token_requests)
        return token

    async def _access_token(self, *, force: bool = False) -> str:
        """Return a live token, minting a new one only when needed."""
        if force or self._token is None or self._monotonic() >= self._token_expires_at:
            return await self._mint_token()
        return self._token

    # -- search -------------------------------------------------------------

    async def _get(self, params: Mapping[str, str], token: str) -> httpx.Response:
        async def do_get() -> httpx.Response:
            return await self._client.get(
                FT_SEARCH_URL,
                params=dict(params),
                headers={**self._headers, "Authorization": f"Bearer {token}"},
            )

        await self._pacer.wait()
        return await with_backoff(self._policy)(do_get)()

    async def _search(
        self, segment: Mapping[str, str], start: int, end: int
    ) -> tuple[FTSearchResponse, int | None]:
        """One ``range`` window; refreshes the token once on a 401 and replays."""
        params: dict[str, str] = {"range": f"{start}-{end}", **segment}
        response = await self._get(params, await self._access_token())
        if response.status_code == 401:
            self._log.info("ft_token_expired_refreshing", scope=dict(segment))
            response = await self._get(params, await self._access_token(force=True))
        if response.status_code == 204:
            return FTSearchResponse(), None
        if response.status_code not in (200, 206):
            response.raise_for_status()
        total = parse_content_range(response.headers.get("Content-Range"))
        return FTSearchResponse.model_validate(response.json()), total

    def _planned_windows(self, total: int | None) -> int:
        """Windows the advertised total implies, inside the 3000-start cap."""
        if total is None or total <= 0:
            return 1
        return min(math.ceil(total / self._window), FT_MAX_START // self._window + 1)

    def _default_segments(self) -> list[Mapping[str, str]]:
        """One unsegmented query (national total) plus one per département."""
        segments: list[Mapping[str, str]] = [{}]
        segments.extend({"departement": code} for code in self._crosswalk.departements())
        return segments

    def fetch(self) -> AsyncIterator[RawRecord]:
        """Walk every segment's ``range`` windows, yielding one RawRecord per offer."""
        return self._fetch()

    async def _fetch(self) -> AsyncIterator[RawRecord]:
        segments = self._segments if self._segments is not None else self._default_segments()
        seen: set[str] = set()
        rows_seen = 0
        for segment in segments:
            if self._budget_spent():
                break
            start = 0
            while True:
                if self._budget_spent():
                    break
                result, total = await self._search(segment, start, start + self._window - 1)
                self.completed_pages += 1
                if start == 0:
                    self.planned_pages += self._planned_windows(total)
                    if not segment and total is not None:
                        self.advertised_count = total
                if not result.resultats:
                    break
                for offre in result.resultats:
                    source_id = pseudonymize(offre.id, self._hmac_key)
                    if source_id in seen:
                        continue
                    seen.add(source_id)
                    rows_seen += 1
                    yield RawRecord(native_id=offre.id, payload=offre.model_dump())
                if len(result.resultats) < self._window:
                    break
                start += self._window
                # A start position above 3000 is rejected by the API.
                if start > FT_MAX_START:
                    break
                if total is not None and start >= total:
                    break

        # Manifest reconciliation: segmented sweeps dedupe across queries, so the
        # advertised per-segment totals are not comparable with the row count.
        # Report what this sweep actually fetched (Increment 3 precedent) and
        # keep the advertised national stock in coverage_limitations.
        self.total_pages = self.completed_pages
        self.total_elements = rows_seen

    def _budget_spent(self) -> bool:
        return self._max_pages is not None and self.completed_pages >= self._max_pages

    # -- normalization ------------------------------------------------------

    def parse(self, raw: RawRecord) -> dict[str, Any]:
        """Extract the source-native fields the allowlist needs."""
        offre = FTOffre.model_validate(raw.payload)
        lieu = offre.lieuTravail
        return {
            "native_id": offre.id,
            "first_published": parse_ft_datetime(offre.dateCreation),
            "last_modified": parse_ft_datetime(offre.dateActualisation),
            "number_of_vacancies": offre.nombrePostes if offre.nombrePostes is not None else 1,
            "rome_code": offre.romeCode,
            "commune": lieu.commune if lieu else None,
            "code_postal": lieu.codePostal if lieu else None,
            "lieu_libelle": lieu.libelle if lieu else None,
        }

    def normalize(self, parsed: dict[str, Any]) -> NormalizedRecord:
        """Map parsed fields onto the SAFE_FIELDS allowlist and pseudonymize the id."""
        region = self._crosswalk.resolve(
            commune=parsed["commune"],
            code_postal=parsed["code_postal"],
            libelle=parsed["lieu_libelle"],
        )
        # ROME is present on every offer; only the ESCO crosswalk is missing.
        occupation_status: MappingStatus = "unmapped" if parsed["rome_code"] else "not_present"
        return NormalizedRecord(
            source=self.source,
            source_id=pseudonymize(parsed["native_id"], self._hmac_key),
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
            esco_occupation_uri=None,
            esco_occupation_label=None,
            occupation_mapping_status=occupation_status,
            occupation_mapping_method="deferred_rome_to_esco",
            source_language="fr",
            jobtech_taxonomy_version="",
            esco_version="1.2.1",
            skill_mappings=[],
            lang="fr",
            number_of_vacancies=max(0, int(parsed["number_of_vacancies"])),
        )
