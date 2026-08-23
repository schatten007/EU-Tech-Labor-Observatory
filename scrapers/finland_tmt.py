"""Finland TyÃ¶markkinatori collector â€” SCRAPER_ROADMAP.md Increment 7.

Official "Jobposting Search API" (*hakurajapinta*) of Job Market Finland /
TyÃ¶markkinatori, served through the KEHA Centre's integration platform **Kipa**
as service **P67**::

    POST https://api.ahtp.fi/kipa/p67/v2/jobpostings        (production)
    POST https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings     (test)
         KIPA-Subscription-Key: <key>
         Content-Type: application/json      body: FiltersV2
      -> 200 application/x-ndjson            one JobPostingV2 per line

Contract pinned on 2026-08-23 from the **live OpenAPI description**
(``https://tyomarkkinatori.fi/jobpostingProvider/swagger/api-docs/P67-tmt-provider-haku-V2``,
19,115 bytes, robots-allowed) plus the technical documentation
(``/jobpostingprovider/documentation/KIPA-search-jobpostings-en.html``), because
the API host itself **cannot be reached without a KEHA-issued IP opening** â€” see
``SCRAPER_FEASIBILITY.md``. Everything below is therefore contract-derived and
respx-tested, not measured on live traffic; the first authorised sweep must
confirm it.

- **Auth.** *"Calls through the Kipa integration platform are authorized using an
  API key mechanism, and the header information of the request must include the
  ``KIPA-Subscription-Key`` provided for Kipa usage."* The OpenAPI description
  instead declares ``bearerAuth`` (HTTP bearer, JWT) with
  ``servers: [https://tyomarkkinatori.fi]`` â€” i.e. it documents the **backend**
  behind the gateway, not the Kipa edge. This collector always sends the
  subscription key and additionally sends ``Authorization: Bearer <token>`` only
  when ``TMT_BEARER_TOKEN`` is configured; a ``401`` refreshes that bearer once
  and replays the identical request (Increment 4 precedent).
- **No pagination, no cursor, no sentinel.** ``FiltersV2`` has no offset, limit,
  page or continuation field: one POST returns one complete result set as an
  NDJSON stream that ends when the body ends. Windowing is done with the
  ``Interval`` filters (``created`` / ``modified`` / ``published`` / ``archived``
  / ``expires``, each ``{from inclusive, to exclusive}``) and the set filters
  (``regionIn``, ``municipalityIn``, ``postingLanguageIn``, ``countryIn``,
  ``occupationIscoIn``, ...). The "cursor" is therefore a **watermark**: the
  maximum ``metadata.lastModified`` seen, persisted to
  ``data/state/finland_tmt_cursor.json`` and replayed as ``modified.from``.
- **Rate limits.** The ``200`` response declares ``RateLimit-Limit``,
  ``RateLimit-Remaining`` and ``RateLimit-Reset`` headers but publishes no
  numbers, so every response's values are logged. Pacing is the charter's 1 s
  floor and ``Retry-After`` is honored on ``429`` via ``scrapers.retry``.

SAFE_FIELDS mapping:

- ``source_id``          = HMAC of ``metadata.externalId`` (a UUID).
- ``first_published``    = ``application.published``, falling back to
  ``metadata.created`` (the schema notes ``published`` *"can be null or absent
  for postings meant to be published immediately"*).
- ``last_modified``      = ``metadata.lastModified``.
- ``removed_at``         = ``metadata.archived`` â€” **source-reported**, so no
  MPSV-style reconciliation pass is needed (Increment 6 precedent).
- ``number_of_vacancies``= ``application.openPositions`` (documented 1..1000).
- ``lang``/``source_language`` = first entry of the required ``languages`` array.
- **Region:** ``location.municipalities`` (KUNTA codes, ``maxLength 3``) then
  ``location.regions`` (MAAKUNTA codes, ``maxLength 2``) through the pinned
  ``data/reference/finland_tmt_region_nuts_2024.csv`` crosswalk (Statistics
  Finland ``kunta_1_20260101#nuts_2_20260101`` Ã— Eurostat GISCO NUTS 2024).
- **Occupation and skills: native ESCO URIs** â€” the first source in this lab to
  populate ``skill_mappings``. The source ships **FINESCO 1.2.0-R8**, whose
  occupation universe is *not* purely ESCO: measured on the published
  distribution, 3,046 of 3,743 concepts are
  ``http://data.europa.eu/esco/occupation/<uuid>``, 619 are ISCO group URIs
  (``esco/isco/C####``) and **78 are Finnish national extensions**
  (``data.tyomarkkinatori.fi/esco/occupation/...``); skills are 15,163 ESCO
  skills plus 220 ISCED-F concepts. Values are therefore classified, never
  guessed â€” see :func:`resolve_occupation` and :func:`resolve_skills`.

Timestamps: every ``date-time`` field in the schema is ``maxLength 26``, exactly
the width of ``YYYY-MM-DDTHH:MM:SS.ffffff`` with **no room for a timezone
designator**, so the source is expected to send naive timestamps. An offset is
honored when present and a naive value is read as UTC â€” an assumption recorded in
``coverage_limitations`` and flagged for confirmation on the first authorised
sweep rather than hidden.

PII and licence compliance: the payload carries ``contacts[{firstName, lastName,
email, telephone}]``, ``owner``/``client`` (business ids, company and office
names, ``householdEmployer``), ``position.title``/``jobDescription``/
``marketingDescription``, ``application.helpText``/``url``, ``externalLinks`` and
``location.workplaceAddress``/``workplacePostalCode``/``workplacePostOffice``.
None of them are declared on the payload models, so they never enter ``parse``;
``NormalizedRecord(extra="forbid")`` is the backstop. The API terms of use
require the source to be indicated (*"Source: Job Market Finland's customer
information system"*, recorded as :data:`TMT_ATTRIBUTION` and the manifest's
``licence_reference``), forbid forwarding postings to third parties and forbid
storing removed postings so that they can still be retrieved â€” all three are
satisfied structurally, because the output holds no posting content at all and
stamps the source's own ``archived`` timestamp as ``removed_at``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, ConfigDict, Field

from scrapers.base import (
    BaseCollector,
    MappingStatus,
    NormalizedRecord,
    RawRecord,
)
from scrapers.retry import RetryPolicy, with_backoff
from scrapers.robots import PacingGate, RobotsDisallowedError, RobotsRule
from scrapers.sanitize import pseudonymize, read_dotenv_value

#: Kipa production gateway. Both Kipa hosts are IP-allowlisted by KEHA.
TMT_KIPA_BASE = "https://api.ahtp.fi"
#: Kipa test gateway (also credential- and IP-gated; not a public sandbox).
TMT_KIPA_QA_BASE = "https://api-qa.ahtp.fi"
TMT_SEARCH_PATH = "/kipa/p67/v2/jobpostings"
TMT_ROBOTS_PATH = "/robots.txt"

TMT_SOURCE_VERSION = "p67-tmt-provider-haku-v2"
TMT_SCOPE_ID = "fi-all-active"
TMT_SCOPE_PARAMS: dict[str, str] = {
    "source": "tmt",
    "country": "FI",
    "api": "p67-tmt-provider-haku-v2",
    "query": "all-active",
    "only_status": "PUBLISHED",
}
TMT_LICENCE_REFERENCE = (
    "https://tyomarkkinatori.fi/en/instructions-and-support/interfaces/"
    "interfaces-for-job-postings/terms-of-use-for-job-market-finlands-job-posting-apis"
)
#: Mandatory attribution from Â§ 2 of the API terms of use.
TMT_ATTRIBUTION = "Source: Job Market Finland's customer information system"
TMT_ACCESS_METHOD = "public-api"
#: The terms require the consuming service to keep postings up to date.
TMT_FRESHNESS_THRESHOLD_HOURS = 24

#: Charter floor; the API publishes no rate-limit numbers, only RateLimit-* headers.
TMT_PACING_SECONDS = 1.0
#: One POST streams a whole result set, so the read window is generous
#: (the lab's 30 s default is a per-page budget, not a per-stream one).
TMT_REQUEST_TIMEOUT_SECONDS = 180.0

TMT_USER_AGENT = (
    "EU-Tech-Labour-Observatory/0.1 (+public job-data research, robots-and-ToS-compliant, "
    "Job Market Finland jobposting search API)"
)

TMT_REFERENCE_FILE = "finland_tmt_region_nuts_2024.csv"
#: Watermark state (gitignored: ``data/*``). Not a server-side cursor â€” the API
#: has none â€” but the maximum ``metadata.lastModified`` the last sweep saw.
TMT_CURSOR_FILE = Path("data/state/finland_tmt_cursor.json")

#: ``onlyStatus`` values accepted by ``FiltersV2``.
TMT_STATUS_PUBLISHED = "PUBLISHED"
TMT_STATUS_ARCHIVED = "ARCHIVED"

#: ``source_type`` values in the pinned crosswalk.
KUNTA_KEY = "kunta"
MAAKUNTA_KEY = "maakunta"
#: A maakunta whose municipalities span more than one NUTS 3 region cannot be
#: resolved from the region code alone; it is written with no code so the
#: collector reports ``ambiguous`` instead of guessing (Increment 6 precedent).
MAAKUNTA_AMBIGUOUS_KEY = "maakunta-ambiguous"

#: Statistics Finland code widths, matching the API's own ``maxLength``.
KUNTA_CODE_WIDTH = 3
MAAKUNTA_CODE_WIDTH = 2

#: ESCO / FINESCO URI namespaces, measured on the source's own distribution.
ESCO_OCCUPATION_URI = re.compile(
    r"^https?://data\.europa\.eu/esco/occupation/[0-9a-fA-F-]{36}$",
)
ESCO_ISCO_GROUP_URI = re.compile(r"^https?://data\.europa\.eu/esco/isco/", re.IGNORECASE)
ESCO_SKILL_URI = re.compile(
    r"^https?://data\.europa\.eu/esco/skill/[0-9a-fA-F-]{36}$",
)
ESCO_ISCED_F_URI = re.compile(r"^https?://data\.europa\.eu/esco/isced-f/", re.IGNORECASE)
#: Finnish national extensions: valid FINESCO concepts, but not ESCO URIs.
FINESCO_NATIONAL_URI = re.compile(r"^https?://data\.tyomarkkinatori\.fi/esco/", re.IGNORECASE)

#: FINESCO release the source ships (from its published ``definitions.zip``).
FINESCO_VERSION = "1.2.0-R8"

TMT_COVERAGE_LIMITATIONS = (
    "Official Job Market Finland (TyÃ¶markkinatori) jobposting search API, service "
    "P67 of the KEHA Centre's Kipa integration platform. Access is restricted: a "
    "KEHA-issued KIPA-Subscription-Key plus a KEHA-side IP opening are both "
    "required, and the right to use the interface is bound to the API user's "
    "Finnish business id (Y-tunnus). Attribution required by the terms of use: "
    f"'{TMT_ATTRIBUTION}'. The API exposes no pagination, cursor or terminal "
    "sentinel: one POST returns one whole result set as an application/x-ndjson "
    "stream, so a sweep is bounded by its FiltersV2 window (onlyStatus plus the "
    "created/modified/published/archived/expires intervals) and by the "
    "--max-rows budget, and the next poll resumes from a client-side watermark "
    "(max metadata.lastModified), not from a server cursor. The source publishes "
    "no rate-limit numbers, only RateLimit-Limit/Remaining/Reset response "
    "headers, which are logged per response. Occupation and skills come from the "
    f"source's own FINESCO {FINESCO_VERSION} distribution, whose universe is not "
    "purely ESCO: ISCO group URIs and Finnish national extension URIs "
    "(data.tyomarkkinatori.fi) are reported as low_confidence and unmapped "
    "respectively rather than written into an ESCO URI field, and ISCED-F "
    "concepts are marked as such in skill_mappings. ESCO labels are left null "
    "(the source's labels are Finnish/Swedish and this project publishes "
    "English). Region is resolved from location.municipalities (KUNTA) then "
    "location.regions (MAAKUNTA) through a pinned Statistics Finland x Eurostat "
    "GISCO NUTS 2024 crosswalk; a posting whose work location is outside Finland "
    "carries no Finnish municipality code and stays region-unmapped. All "
    "date-time fields are maxLength 26, i.e. too narrow for a timezone "
    "designator, so a naive timestamp is read as UTC - an assumption to confirm "
    "on the first authorised sweep. Postings published here are automatically "
    "re-exported to the EURES portal, so this stock overlaps the EURES scope and "
    "the two must not be summed."
)


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def tmt_credentials() -> tuple[str, str | None]:
    """Load the Kipa subscription key (and optional bearer) from env or ``.env``.

    Returns ``(subscription_key, bearer_token_or_None)``. Raises
    :class:`RuntimeError` **before any network call** when the key is missing, so
    a sweep never opens a socket to an IP-allowlisted host it cannot use.
    Credentials are never hardcoded, logged or committed.
    """
    key = os.environ.get("TMT_KIPA_SUBSCRIPTION_KEY") or read_dotenv_value(
        "TMT_KIPA_SUBSCRIPTION_KEY"
    )
    bearer = os.environ.get("TMT_BEARER_TOKEN") or read_dotenv_value("TMT_BEARER_TOKEN")
    if not key:
        raise RuntimeError(
            "TMT_KIPA_SUBSCRIPTION_KEY is not set. The Job Market Finland jobposting "
            "search API (P67 via Kipa) is activation-gated: an organisation with a "
            "Finnish business id must submit the KEHA activation notification and "
            "accept the API terms of use, after which KEHA issues the subscription "
            "key AND opens the caller's IP address on api.ahtp.fi. Add the key to "
            ".env as TMT_KIPA_SUBSCRIPTION_KEY (and TMT_BEARER_TOKEN if a bearer "
            "token is issued too). Credentials must never be hardcoded."
        )
    return key, bearer


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_tmt_datetime(value: str | None) -> datetime | None:
    """Parse a P67 ``date-time`` (``maxLength 26``), reading naive values as UTC.

    The field width leaves no room for a timezone designator, so the source is
    expected to send ``2026-03-24T10:15:30.123456``. An explicit offset (or a
    trailing ``Z``) is honored when present.
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def normalize_code(value: str | None, width: int) -> str:
    """Fold a Statistics Finland code to its canonical zero-padded form.

    ``"74"`` and ``"074"`` are the same municipality, so both fold to ``"074"``.
    Shared by the collector and :mod:`scrapers.reference_finland` so the pinned
    keys and the lookup keys cannot drift apart.
    """
    if value is None:
        return ""
    text = str(value).strip().upper()
    if not text:
        return ""
    return text.zfill(width) if len(text) < width else text


def normalize_kunta_code(value: str | None) -> str:
    """Canonical KUNTA (municipality) code, e.g. ``"74"`` -> ``"074"``."""
    return normalize_code(value, KUNTA_CODE_WIDTH)


def normalize_maakunta_code(value: str | None) -> str:
    """Canonical MAAKUNTA (region) code, e.g. ``"1"`` -> ``"01"``."""
    return normalize_code(value, MAAKUNTA_CODE_WIDTH)


def rate_limit_headers(response: httpx.Response) -> dict[str, str]:
    """The three ``RateLimit-*`` values the API declares, when present."""
    names = ("RateLimit-Limit", "RateLimit-Remaining", "RateLimit-Reset")
    return {name: response.headers[name] for name in names if name in response.headers}


# ---------------------------------------------------------------------------
# Source-native payload models (extra="ignore": PII fields never enter parse)
# ---------------------------------------------------------------------------


class TMTMetadata(BaseModel):
    """``JobPostingV2.metadata`` â€” the identifier and the three timestamps."""

    model_config = ConfigDict(extra="ignore")

    externalId: str | None = None
    created: str | None = None
    lastModified: str | None = None
    archived: str | None = None


class TMTApplication(BaseModel):
    """``JobPostingV2.application``; ``helpText``/``url`` deliberately undeclared."""

    model_config = ConfigDict(extra="ignore")

    published: str | None = None
    expires: str | None = None
    openPositions: int | None = None


class TMTPosition(BaseModel):
    """``JobPostingV2.position`` â€” occupation and skill URIs only.

    ``title``, ``jobDescription``, ``marketingDescription``, ``wagePrincipalInfo``,
    ``partTimeInfo`` and ``permitCardsDescription`` are free text and are not
    declared, so they never enter the parse step.
    """

    model_config = ConfigDict(extra="ignore")

    mainOccupation: str | None = None
    occupations: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class TMTLocation(BaseModel):
    """``JobPostingV2.location`` â€” codes only.

    ``workplaceAddress``, ``workplacePostalCode``, ``workplacePostOffice`` and
    ``workplaceName`` are identifying and are not declared.
    """

    model_config = ConfigDict(extra="ignore")

    countries: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    municipalities: list[str] = Field(default_factory=list)


class TMTJobPosting(BaseModel):
    """The allowlist-relevant slice of one ``JobPostingV2`` NDJSON line.

    ``client``, ``owner``, ``contacts``, ``externalLinks`` and
    ``descriptionsContentType`` are **not declared**: employer, business ids and
    contact people never enter the pipeline, not even into ``RawRecord``.
    """

    model_config = ConfigDict(extra="ignore")

    languages: list[str] = Field(default_factory=list)
    metadata: TMTMetadata | None = None
    position: TMTPosition | None = None
    location: TMTLocation | None = None
    application: TMTApplication | None = None


# ---------------------------------------------------------------------------
# Watermark ("cursor") state
# ---------------------------------------------------------------------------


class StreamWatermark(BaseModel):
    """Poll state for a source that has no server-side cursor.

    ``modified_from`` is the maximum ``metadata.lastModified`` the previous sweep
    saw; the next poll sends it as ``FiltersV2.modified.from`` (inclusive), so a
    daily run streams only what changed.
    """

    model_config = ConfigDict(extra="ignore")

    modified_from: str | None = None
    only_status: str | None = None
    sweep_id: str | None = None
    updated_at: str | None = None
    rows_seen: int | None = None


def load_watermark(path: Path = TMT_CURSOR_FILE) -> StreamWatermark | None:
    """Read the persisted watermark, or ``None`` when absent or unreadable."""
    if not path.exists():
        return None
    try:
        return StreamWatermark.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def save_watermark(watermark: StreamWatermark, path: Path = TMT_CURSOR_FILE) -> None:
    """Persist the watermark (creating ``data/state/`` when needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(watermark.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Region crosswalk (NUTS 2024)
# ---------------------------------------------------------------------------


class RegionResolution(BaseModel):
    """Outcome of the KUNTA/MAAKUNTA -> NUTS 2024 resolution for one posting."""

    nuts_code: str | None = None
    nuts_label: str | None = None
    status: MappingStatus = "unmapped"
    method: str = "not_available"


class OccupationResolution(BaseModel):
    """Outcome of the FINESCO occupation -> ESCO 1.2.1 resolution."""

    uri: str | None = None
    status: MappingStatus = "not_present"
    confidence: str | None = None
    method: str = "not_available"


class FinlandCrosswalk:
    """Loads the pinned KUNTA/MAAKUNTA -> NUTS 2024 table and resolves regions.

    Matching rules, first hit wins:

    1. ``location.municipalities`` (KUNTA codes) â€” a single distinct NUTS 3
       result is ``mapped``; several distinct results are ``ambiguous`` (a
       posting advertised across two regions cannot have one NUTS 3 code).
    2. ``location.regions`` (MAAKUNTA codes) â€” a Finnish maakunta *is* a NUTS 3
       region (verified when the crosswalk is built), so a single hit is
       ``mapped`` too; several are ``ambiguous``, and a maakunta recorded as
       ambiguous in the crosswalk is reported ``ambiguous`` rather than guessed.
    3. Codes present but unknown -> ``unmapped``; no codes at all ->
       ``not_present``.
    """

    def __init__(self, reference_dir: Path) -> None:
        path = reference_dir / TMT_REFERENCE_FILE
        if not path.exists():
            raise FileNotFoundError(
                f"missing Finland crosswalk reference: {path} "
                "(rebuild with `python -m scrapers.reference_finland`)"
            )
        self._kunta: dict[str, tuple[str, str]] = {}
        self._maakunta: dict[str, tuple[str, str]] = {}
        self._maakunta_ambiguous: set[str] = set()
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                source_type = (row.get("source_type") or "").strip()
                code = (row.get("source_code") or "").strip().upper()
                pair = ((row.get("nuts_code") or "").strip(), (row.get("nuts_label") or "").strip())
                if not code:
                    continue
                if source_type == KUNTA_KEY:
                    self._kunta[code] = pair
                elif source_type == MAAKUNTA_KEY:
                    self._maakunta[code] = pair
                elif source_type == MAAKUNTA_AMBIGUOUS_KEY:
                    self._maakunta_ambiguous.add(code)
        if not self._kunta and not self._maakunta:
            raise ValueError(f"Finland crosswalk reference is empty: {path}")

    def kunnat(self) -> list[str]:
        """The municipality codes the crosswalk resolves (sorted, stable)."""
        return sorted(self._kunta)

    def maakunnat(self) -> list[str]:
        """The region codes the crosswalk resolves (sorted, stable)."""
        return sorted(self._maakunta)

    def lookup_kunta(self, code: str | None) -> tuple[str, str] | None:
        """NUTS 3 code and label for a municipality code, or ``None``."""
        return self._kunta.get(normalize_kunta_code(code))

    def lookup_maakunta(self, code: str | None) -> tuple[str, str] | None:
        """NUTS 3 code and label for a region code, or ``None``."""
        return self._maakunta.get(normalize_maakunta_code(code))

    def maakunta_is_ambiguous(self, code: str | None) -> bool:
        """True when the region code spans several NUTS 3 regions in the crosswalk."""
        return normalize_maakunta_code(code) in self._maakunta_ambiguous

    def _resolve_codes(
        self,
        codes: Sequence[str],
        *,
        lookup: str,
    ) -> tuple[dict[str, str], bool, bool]:
        """Distinct NUTS 3 hits for ``codes``, plus (saw_code, saw_ambiguous)."""
        hits: dict[str, str] = {}
        saw_code = False
        saw_ambiguous = False
        for raw in codes:
            code = (raw or "").strip()
            if not code:
                continue
            saw_code = True
            if lookup == MAAKUNTA_KEY:
                if self.maakunta_is_ambiguous(code):
                    saw_ambiguous = True
                    continue
                hit = self.lookup_maakunta(code)
            else:
                hit = self.lookup_kunta(code)
            if hit is not None and hit[0]:
                hits[hit[0]] = hit[1]
        return hits, saw_code, saw_ambiguous

    def resolve(
        self,
        *,
        municipalities: Sequence[str] | None = None,
        regions: Sequence[str] | None = None,
    ) -> RegionResolution:
        """Resolve one posting's location codes to a NUTS 2024 region."""
        kunta_hits, saw_kunta, _ = self._resolve_codes(list(municipalities or ()), lookup=KUNTA_KEY)
        if len(kunta_hits) == 1:
            code = next(iter(kunta_hits))
            return RegionResolution(
                nuts_code=code,
                nuts_label=kunta_hits[code],
                status="mapped",
                method="tmt_kunta_nuts3",
            )
        if len(kunta_hits) > 1:
            return RegionResolution(status="ambiguous", method="tmt_kunta_multiple_nuts3")

        maakunta_hits, saw_maakunta, maakunta_ambiguous = self._resolve_codes(
            list(regions or ()), lookup=MAAKUNTA_KEY
        )
        if len(maakunta_hits) == 1:
            code = next(iter(maakunta_hits))
            return RegionResolution(
                nuts_code=code,
                nuts_label=maakunta_hits[code],
                status="mapped",
                method="tmt_maakunta_nuts3",
            )
        if len(maakunta_hits) > 1:
            return RegionResolution(status="ambiguous", method="tmt_maakunta_multiple_nuts3")
        if maakunta_ambiguous:
            return RegionResolution(status="ambiguous", method="tmt_maakunta_ambiguous_code")
        if saw_kunta or saw_maakunta:
            return RegionResolution(status="unmapped", method="tmt_unknown_region_code")
        return RegionResolution(status="not_present", method="not_available")


def crosswalk_reference_hashes(reference_dir: Path) -> str:
    """SHA-256 of the pinned crosswalk CSV (content only)."""
    digest = hashlib.sha256()
    with (reference_dir / TMT_REFERENCE_FILE).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return f"{TMT_REFERENCE_FILE}:{digest.hexdigest()}"


# ---------------------------------------------------------------------------
# ESCO resolution (FINESCO is not purely ESCO)
# ---------------------------------------------------------------------------


def resolve_occupation(
    main_occupation: str | None, occupations: Iterable[str]
) -> OccupationResolution:
    """Pick the ESCO occupation URI from ``mainOccupation`` / ``occupations``.

    ``mainOccupation`` is the posting's declared main occupation and wins; the
    ``occupations`` array is the fallback, scanned in order. Only the
    ``http://data.europa.eu/esco/occupation/<uuid>`` namespace can populate
    ``esco_occupation_uri``. The other FINESCO namespaces are reported, never
    coerced:

    - an **ISCO group** URI (``esco/isco/C2511``) is a valid but coarser concept
      scheme, so the row is ``low_confidence`` with **no URI written** â€” writing
      a group URI into an occupation field would misstate the concept;
    - a **Finnish national extension** (``data.tyomarkkinatori.fi/esco/...``) is
      not an ESCO concept at all -> ``unmapped``;
    - anything else that is present but unrecognised -> ``unmapped``;
    - nothing at all -> ``not_present``.

    ``occupation_mapping_confidence`` stays ``None``: the source attaches no
    score to the URI (unlike NAV's ``categoryList``), and asserting "high"
    without a signal would be an overclaim.
    """
    candidates = [
        value.strip()
        for value in (main_occupation, *occupations)
        if isinstance(value, str) and value.strip()
    ]
    for candidate in candidates:
        if ESCO_OCCUPATION_URI.match(candidate):
            return OccupationResolution(
                uri=candidate,
                status="mapped",
                method="finesco_esco_occupation_uri",
            )
    if not candidates:
        return OccupationResolution(status="not_present", method="not_available")
    if any(ESCO_ISCO_GROUP_URI.match(candidate) for candidate in candidates):
        return OccupationResolution(status="low_confidence", method="finesco_isco_group_uri_only")
    if any(FINESCO_NATIONAL_URI.match(candidate) for candidate in candidates):
        return OccupationResolution(status="unmapped", method="finesco_national_extension_uri")
    return OccupationResolution(status="unmapped", method="finesco_unrecognised_occupation_uri")


def _skill_element(status: MappingStatus, method: str, uri: str | None = None) -> dict[str, str]:
    """One ``skill_mappings`` element in the shape ``stg_skill_mappings.sql`` reads.

    ``uri`` is **omitted** rather than set to ``None`` when no ESCO skill URI
    applies: ``NormalizedRecord.skill_mappings`` is typed ``list[dict[str, str]]``,
    and a missing JSON key reads as ``NULL`` through ``->>'uri'`` exactly like an
    explicit null would. ``label`` is likewise omitted â€” the source's labels are
    Finnish/Swedish and this project publishes English (Increment 6 precedent).
    """
    element = {
        "status": status,
        "method": method,
        "jobtech_taxonomy_version": "",
        "esco_version": "1.2.1",
    }
    if uri:
        element["uri"] = uri
    return element


def resolve_skills(skills: Iterable[str]) -> list[dict[str, str]]:
    """Map ``position.skills`` onto ``skill_mappings``, one element per skill.

    Element order is the source's order, so ``skill_ordinal`` downstream is the
    posting's own ordering. Namespaces are classified the same way as
    occupations: ESCO skill URIs are ``mapped``, ISCED-F concepts are
    ``low_confidence`` (a field-of-education concept, not a skill), national
    extensions and unrecognised strings are ``unmapped``. An empty array yields
    an empty list â€” the row simply has no skill outcome, which is different from
    a skill that failed to map.
    """
    elements: list[dict[str, str]] = []
    for raw in skills:
        if not isinstance(raw, str) or not raw.strip():
            continue
        value = raw.strip()
        if ESCO_SKILL_URI.match(value):
            elements.append(_skill_element("mapped", "finesco_esco_skill_uri", value))
        elif ESCO_ISCED_F_URI.match(value):
            elements.append(_skill_element("low_confidence", "finesco_isced_f_uri"))
        elif FINESCO_NATIONAL_URI.match(value):
            elements.append(_skill_element("unmapped", "finesco_national_extension_uri"))
        else:
            elements.append(_skill_element("unmapped", "finesco_unrecognised_skill_uri"))
    return elements


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class FinlandTMTCollector(BaseCollector):
    """Collector for the Job Market Finland jobposting search API (P67 via Kipa).

    One paced, robots-checked ``POST`` streams the whole filtered result set as
    NDJSON; the collector folds it into SAFE_FIELDS rows, persists a watermark
    for the next poll, and never opens a socket without a subscription key.
    """

    source: ClassVar[str] = "tmt"
    country: ClassVar[str] = "FI"

    def __init__(
        self,
        *,
        scope_id: str,
        sweep_id: str,
        observed_at: datetime,
        hmac_key: bytes,
        subscription_key: str,
        bearer_token: str | None = None,
        base_url: str = TMT_KIPA_BASE,
        reference_dir: Path = Path("data/reference"),
        only_status: str = TMT_STATUS_PUBLISHED,
        modified_from: str | None = None,
        max_rows: int | None = None,
        use_cursor: bool = True,
        cursor_path: Path | None = TMT_CURSOR_FILE,
        pacing_interval: float = TMT_PACING_SECONDS,
        policy: RetryPolicy | None = None,
        timeout: float = TMT_REQUEST_TIMEOUT_SECONDS,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(
            scope_id=scope_id, sweep_id=sweep_id, observed_at=observed_at, timeout=timeout
        )
        if len(hmac_key) < 32:
            raise ValueError("hmac_key must be at least 32 bytes")
        if not subscription_key:
            raise ValueError("TyÃ¶markkinatori requires a KIPA-Subscription-Key for every request")
        if only_status not in (TMT_STATUS_PUBLISHED, TMT_STATUS_ARCHIVED):
            raise ValueError(
                f"only_status must be {TMT_STATUS_PUBLISHED} or {TMT_STATUS_ARCHIVED}, "
                f"got {only_status!r}"
            )
        self._hmac_key = hmac_key
        self._subscription_key = subscription_key
        self._bearer_token = bearer_token
        self._base_url = base_url.rstrip("/")
        self._crosswalk = FinlandCrosswalk(reference_dir)
        self._only_status = only_status
        self._modified_from = modified_from
        self._max_rows = max_rows
        self._use_cursor = use_cursor
        self._cursor_path = cursor_path
        self._pacing_interval = pacing_interval
        self._policy = policy or RetryPolicy()
        self._pacer = PacingGate(min_interval=pacing_interval)
        self._sleeper = sleeper
        self._robots: RobotsRule | None = None
        self._headers = {
            "User-Agent": TMT_USER_AGENT,
            "Accept": "application/x-ndjson",
            "Content-Type": "application/json",
        }
        self.total_elements = 0
        self.total_pages = 0
        self.completed_pages = 0
        #: NDJSON streams completed (one per POST; the API has no pagination).
        self.streams_completed = 0
        #: Non-empty NDJSON lines received.
        self.lines_seen = 0
        #: Lines that were not valid JSON (counted and skipped, never guessed).
        self.malformed_lines = 0
        #: Valid JSON lines with no ``metadata.externalId`` (cannot be pseudonymized).
        self.rows_without_id = 0
        #: Rows dropped because their HMAC ``source_id`` was already written.
        self.duplicates_dropped = 0
        #: Rows carrying a native ESCO 1.2.1 occupation URI.
        self.rows_with_esco_occupation = 0
        #: Rows with at least one ``skill_mappings`` element.
        self.rows_with_skills = 0
        #: Total ``skill_mappings`` elements written across the sweep.
        self.skill_elements = 0
        #: Rows carrying a source-reported ``removed_at`` (``metadata.archived``).
        self.rows_removed = 0
        #: Bearer refresh-and-replay cycles (only possible when a bearer is set).
        self.token_refreshes = 0
        #: True when ``--max-rows`` stopped the stream before its end.
        self.truncated_by_budget = False
        #: Highest ``metadata.lastModified`` seen, persisted as the next watermark.
        self.watermark: str | None = None
        #: ``modified.from`` this sweep actually sent, if any.
        self.modified_from_used: str | None = None
        #: Last ``RateLimit-*`` values observed (the API publishes no numbers).
        self.rate_limit: dict[str, str] = {}

    # -- URLs ---------------------------------------------------------------

    @property
    def search_url(self) -> str:
        """The P67 search endpoint on the configured Kipa gateway."""
        return f"{self._base_url}{TMT_SEARCH_PATH}"

    @property
    def robots_url(self) -> str:
        """``robots.txt`` on the configured Kipa gateway."""
        return f"{self._base_url}{TMT_ROBOTS_PATH}"

    # -- robots gate --------------------------------------------------------

    def _backoff(
        self, func: Callable[[], Awaitable[httpx.Response]]
    ) -> Callable[[], Awaitable[httpx.Response]]:
        """Wrap one call in the shared retry policy.

        ``sleeper`` is injectable so a test can assert that ``Retry-After`` is
        honored without actually waiting; production uses ``asyncio.sleep``.
        """
        if self._sleeper is not None:
            return with_backoff(self._policy, sleeper=self._sleeper)(func)
        return with_backoff(self._policy)(func)

    async def _load_robots(self) -> RobotsRule:
        """Fetch and parse ``robots.txt`` once per sweep, before any other URL.

        The Kipa gateway is IP-allowlisted, so an unauthorised caller cannot even
        complete the TCP handshake. That transport failure is turned into an
        explicit message instead of a bare timeout, because it is the expected
        state until KEHA opens the caller's address.
        """
        if self._robots is not None:
            return self._robots

        async def do_get() -> httpx.Response:
            return await self._client.get(self.robots_url, headers={"User-Agent": TMT_USER_AGENT})

        await self._pacer.wait()
        try:
            response = await self._backoff(do_get)()
        except httpx.TransportError as error:
            raise RuntimeError(
                f"cannot reach {self.robots_url}: the Kipa gateway is IP-allowlisted, so "
                "KEHA must open this host's address for the caller before any request "
                f"(see SCRAPER_FEASIBILITY.md, Increment 7). Underlying error: {error}"
            ) from error
        served = response.status_code == 200 and "text/plain" in (
            response.headers.get("content-type") or ""
        )
        rule = RobotsRule(response.text if served else None)
        self._robots = rule
        delay = rule.crawl_delay(TMT_USER_AGENT)
        self._log.info(
            "tmt_robots_loaded",
            status=response.status_code,
            served=served,
            bytes=len(response.content),
            crawl_delay=delay,
            search_allowed=rule.can_fetch(self.search_url, TMT_USER_AGENT),
        )
        if delay is not None and delay > self._pacing_interval:
            self._pacer = PacingGate(min_interval=delay)
        return rule

    def assert_allowed(self, url: str) -> None:
        """Raise :class:`RobotsDisallowedError` unless robots.txt permits ``url``."""
        rule = self._robots
        if rule is None:
            raise RobotsDisallowedError(f"robots.txt not loaded before requesting {url}")
        if not rule.can_fetch(url, TMT_USER_AGENT):
            raise RobotsDisallowedError(f"robots.txt disallows {url} for {TMT_USER_AGENT}")

    # -- request ------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        """Kipa subscription key, plus a bearer token only when one is configured."""
        headers = {"KIPA-Subscription-Key": self._subscription_key}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers

    def filters(self) -> dict[str, Any]:
        """The ``FiltersV2`` body for this sweep.

        ``onlyStatus`` selects the active (``PUBLISHED``) or archived set, and
        ``modified.from`` carries the watermark when a previous sweep left one.
        No other filter is sent by default: the API has no pagination, so adding
        an unverified filter could silently drop rows.
        """
        body: dict[str, Any] = {"onlyStatus": self._only_status}
        if self.modified_from_used:
            body["modified"] = {"from": self.modified_from_used}
        return body

    async def _post_stream(self, body: Mapping[str, Any]) -> httpx.Response:
        """One paced, robots-checked, retried streaming POST.

        Retryable statuses (429/5xx) are drained and closed before being handed
        back to :func:`scrapers.retry.with_backoff`, so a retry never leaks an
        open connection; a successful response is returned **unread** so the
        NDJSON body can be consumed line by line.
        """
        self.assert_allowed(self.search_url)
        url = self.search_url
        headers = {**self._headers, **self._auth_headers()}

        async def do_post() -> httpx.Response:
            request = self._client.build_request("POST", url, json=dict(body), headers=headers)
            response = await self._client.send(request, stream=True)
            if response.status_code in self._policy.retry_statuses:
                await response.aread()
                await response.aclose()
            return response

        await self._pacer.wait()
        return await self._backoff(do_post)()

    async def _open_stream(self, body: Mapping[str, Any]) -> httpx.Response:
        """Open the NDJSON stream, refreshing the bearer once on a ``401``."""
        response = await self._post_stream(body)
        if response.status_code == 401 and self._bearer_token:
            await response.aread()
            await response.aclose()
            self.token_refreshes += 1
            self._log.info("tmt_bearer_rejected_refreshing", refreshes=self.token_refreshes)
            self._bearer_token = tmt_credentials()[1]
            response = await self._post_stream(body)
        self.rate_limit = rate_limit_headers(response)
        if response.status_code != 200:
            await response.aread()
            await response.aclose()
            response.raise_for_status()
        return response

    # -- fetch --------------------------------------------------------------

    def fetch(self) -> AsyncIterator[RawRecord]:
        """Stream the filtered result set, yielding one RawRecord per posting."""
        return self._fetch()

    async def _fetch(self) -> AsyncIterator[RawRecord]:
        await self._load_robots()
        self.modified_from_used = self._resolve_modified_from()
        body = self.filters()
        self._log.info("tmt_stream_open", filters=body, base_url=self._base_url)

        seen: set[str] = set()
        rows = 0
        response = await self._open_stream(body)
        try:
            async for line in response.aiter_lines():
                text = line.strip()
                if not text:
                    continue
                self.lines_seen += 1
                posting = self._parse_line(text)
                if posting is None:
                    continue
                native_id = (posting.metadata.externalId if posting.metadata else None) or ""
                if not native_id.strip():
                    self.rows_without_id += 1
                    continue
                source_id = pseudonymize(native_id, self._hmac_key)
                if source_id in seen:
                    self.duplicates_dropped += 1
                    continue
                seen.add(source_id)
                self._advance_watermark(posting)
                rows += 1
                # Model dump only: employer, contacts, descriptions, URLs and
                # addresses are undeclared and are already gone at this point.
                yield RawRecord(native_id=native_id, payload=posting.model_dump())
                if self._max_rows is not None and rows >= self._max_rows:
                    self.truncated_by_budget = True
                    break
        finally:
            await response.aclose()

        self.streams_completed += 1
        self.completed_pages = self.streams_completed
        self.total_pages = self.streams_completed
        self.total_elements = rows
        if self.lines_seen and rows == 0:
            raise RuntimeError(
                f"schema drift: {self.lines_seen} NDJSON line(s) received but none carried a "
                f"usable metadata.externalId ({self.malformed_lines} malformed, "
                f"{self.rows_without_id} without an id) â€” refusing to write an empty partition"
            )
        self._persist_watermark(rows)
        self._log.info(
            "tmt_sweep_summary",
            streams=self.streams_completed,
            lines=self.lines_seen,
            rows=rows,
            malformed_lines=self.malformed_lines,
            rows_without_id=self.rows_without_id,
            duplicates_dropped=self.duplicates_dropped,
            rows_with_esco_occupation=self.rows_with_esco_occupation,
            rows_with_skills=self.rows_with_skills,
            skill_elements=self.skill_elements,
            rows_removed=self.rows_removed,
            truncated_by_budget=self.truncated_by_budget,
            rate_limit=self.rate_limit,
        )

    def _parse_line(self, text: str) -> TMTJobPosting | None:
        """Validate one NDJSON line, tolerating only unparseable JSON.

        A line that is not JSON is counted and skipped (one corrupt line must not
        abort a whole stream), but a line whose *structure* is wrong raises
        through pydantic: that is schema drift, not noise, and it must be loud.
        """
        try:
            payload = json.loads(text)
        except ValueError:
            self.malformed_lines += 1
            return None
        if not isinstance(payload, dict):
            self.malformed_lines += 1
            return None
        return TMTJobPosting.model_validate(payload)

    def _resolve_modified_from(self) -> str | None:
        """The ``modified.from`` value for this sweep (explicit wins over cursor)."""
        if self._modified_from:
            return self._modified_from
        if not self._use_cursor or self._cursor_path is None:
            return None
        watermark = load_watermark(self._cursor_path)
        if watermark is None or not watermark.modified_from:
            return None
        if watermark.only_status and watermark.only_status != self._only_status:
            # A PUBLISHED watermark says nothing about the ARCHIVED set.
            return None
        self._log.info("tmt_watermark_resumed", modified_from=watermark.modified_from)
        return watermark.modified_from

    def _advance_watermark(self, posting: TMTJobPosting) -> None:
        """Track the highest ``metadata.lastModified`` string seen this sweep."""
        value = (posting.metadata.lastModified if posting.metadata else None) or ""
        value = value.strip()
        if not value:
            return
        if self.watermark is None or value > self.watermark:
            self.watermark = value

    def _persist_watermark(self, rows: int) -> None:
        """Persist the watermark so the next poll streams only what changed."""
        if self._cursor_path is None or self.watermark is None or self.truncated_by_budget:
            return
        save_watermark(
            StreamWatermark(
                modified_from=self.watermark,
                only_status=self._only_status,
                sweep_id=self.sweep_id,
                updated_at=datetime.now(UTC).isoformat(),
                rows_seen=rows,
            ),
            self._cursor_path,
        )

    # -- normalization ------------------------------------------------------

    def parse(self, raw: RawRecord) -> dict[str, Any]:
        """Extract the source-native fields the allowlist needs from one posting."""
        posting = TMTJobPosting.model_validate(raw.payload)
        metadata = posting.metadata
        application = posting.application
        position = posting.position
        location = posting.location
        languages = [
            value.strip().lower() for value in posting.languages if value and value.strip()
        ]
        return {
            "native_id": raw.native_id,
            "first_published": parse_tmt_datetime(
                (application.published if application else None)
                or (metadata.created if metadata else None)
            ),
            "last_modified": parse_tmt_datetime(metadata.lastModified if metadata else None),
            "removed_at": parse_tmt_datetime(metadata.archived if metadata else None),
            "number_of_vacancies": (
                application.openPositions
                if application and application.openPositions is not None
                else 1
            ),
            "main_occupation": position.mainOccupation if position else None,
            "occupations": list(position.occupations) if position else [],
            "skills": list(position.skills) if position else [],
            "municipalities": list(location.municipalities) if location else [],
            "regions": list(location.regions) if location else [],
            "language": languages[0] if languages else "fi",
        }

    def normalize(self, parsed: dict[str, Any]) -> NormalizedRecord:
        """Map parsed fields onto the SAFE_FIELDS allowlist and pseudonymize the id."""
        region = self._crosswalk.resolve(
            municipalities=parsed["municipalities"], regions=parsed["regions"]
        )
        occupation = resolve_occupation(parsed["main_occupation"], parsed["occupations"])
        skills = resolve_skills(parsed["skills"])
        if occupation.uri is not None:
            self.rows_with_esco_occupation += 1
        if skills:
            self.rows_with_skills += 1
            self.skill_elements += len(skills)
        if parsed["removed_at"] is not None:
            self.rows_removed += 1
        return NormalizedRecord(
            source=self.source,
            source_id=pseudonymize(parsed["native_id"], self._hmac_key),
            scope_id=self.scope_id,
            sweep_id=self.sweep_id,
            observed_at=self.observed_at,
            first_published=parsed["first_published"],
            last_modified=parsed["last_modified"],
            removed_at=parsed["removed_at"],
            nuts_code=region.nuts_code,
            nuts_label=region.nuts_label,
            region_mapping_status=region.status,
            region_mapping_method=region.method,
            country=self.country,
            esco_occupation_uri=occupation.uri,
            esco_occupation_label=None,
            occupation_mapping_status=occupation.status,
            occupation_mapping_confidence=occupation.confidence,
            occupation_mapping_method=occupation.method,
            source_language=parsed["language"],
            jobtech_taxonomy_version="",
            esco_version="1.2.1",
            skill_mappings=skills,
            lang=parsed["language"],
            number_of_vacancies=max(0, int(parsed["number_of_vacancies"])),
        )
