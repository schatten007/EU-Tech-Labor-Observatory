"""NAV stillings-feed collector — SCRAPER_ROADMAP.md Increment 6 (Norway).

Official JSON feed of the job ads registered with Nav (arbeidsplassen.no), the
Norwegian public employment service. Norwegian law requires employers to report
vacancies to Nav, and the feed carries every ad and every state change since
~2019:

    GET https://pam-stilling-feed.nav.no/api/publicToken       -> text/plain JWT
    GET https://pam-stilling-feed.nav.no/api/v1/feed           -> seek page (1000 items)
        Authorization: Bearer <jwt>, If-Modified-Since: <RFC 1123>
    GET https://pam-stilling-feed.nav.no/api/v1/feed/<page-id> -> next page
        If-None-Match: <etag>                                  -> 304 when unchanged
    GET https://pam-stilling-feed.nav.no/api/v1/feedentry/<ad-uuid> -> ad detail

Contract pinned live on 2026-08-22 and re-verified on 2026-08-23:

- **robots.txt is ABSENT** on the feed host (404, a Javalin JSON error body), so
  nothing is disallowed; it is still fetched before any other request and
  :class:`~scrapers.robots.RobotsRule` gates every URL, exactly as on VDAB.
- **Auth.** An unauthenticated ``GET /api/v1/feed`` answers **401** with no
  ``WWW-Authenticate`` header: bearer-token access is the only access mode, so
  the token plus the accepted ToS is the operative permission (the keyed-API
  reading established for Adzuna in Increment 3 and France Travail in
  Increment 4). ``NAV_FEED_TOKEN`` (a private consumer token) is used when set,
  otherwise the public experimentation token is fetched at runtime. The public
  token "will rotate at irregular intervals", so a **401 mid-sweep refreshes the
  token once and replays the request** (the France Travail pattern) and is
  logged; no token is ever committed, printed or logged.
- **Pagination.** Exactly **1,000 items per page**; ``next_url`` is
  ``/api/v1/feed/<uuid>`` and ``next_id`` equals the page's own ``ETag``. The end
  of the feed is ``next_url`` **and** ``next_id`` both ``null`` (reproduced live
  by seeking 20 minutes back: 1 item, both null), after which a consumer
  re-polls the same page.
- **Revalidation, corrected against NAV's own docs.** Re-requesting a page URL
  with **``If-None-Match`` alone returns 304 with a 0-byte body**; adding
  ``If-Modified-Since`` to the same request makes the API **re-seek** and answer
  200 (verified live), and a stale ETag answers 200. NAV's documented pseudocode
  sends both headers together; this collector deliberately sends ``If-None-Match``
  only when revalidating a page and ``If-Modified-Since`` only when seeking.
  **304 means "unchanged", not an error:** it is not in
  ``scrapers.retry.DEFAULT_RETRY_STATUSES`` and it never breaks manifest
  reconciliation.
- **``If-Modified-Since`` seeks.** Without it the feed starts at the beginning of
  history (2019 ads); with a 2-day value the first page began at
  ``2026-08-21T01:32``. Measured density: 1,000 items span **4–8 h** of feed
  time, i.e. roughly **3,000–6,000 events/day**. Ads are never active longer
  than ~6 months, so a window beyond :data:`NAV_MAX_SINCE_DAYS` is pointless.
- **Event log, not a snapshot.** "Each change to an ad will generate a new entry
  in the feed, and the latest entry will contain the current state of the ad", so
  a ``uuid`` recurs many times and only its **latest** state is written. The fold
  is keyed on the **HMAC ``source_id``**, never on the native ``uuid``.
- **Details are one paced request each** and carry no ``ETag``/``Last-Modified``,
  so revalidation applies to feed pages only. INACTIVE details are usually
  content-masked: measured **2 of 20 (10%)** still carried ``ad_content`` (the
  other 18 were 111–112 bytes of ``{uuid,status,sistEndret}``), because NAV masks
  ads that are *actively stopped* rather than merely expired. Spending ~9 paced
  requests per usable payload is not worth it, so **INACTIVE details are never
  fetched**: an INACTIVE row is written from the feed event alone, which already
  carries everything it needs (``sistEndret`` and ``municipal``).

SAFE_FIELDS mapping:

- ``source_id``        = HMAC of the ad ``uuid``.
- ``first_published``  = ``ad_content.published``; ``last_modified`` =
  ``ad_content.updated``, falling back to the feed event's ``sistEndret`` when a
  row has no detail payload (``sistEndret`` is the ad's own last-change stamp).
- ``removed_at``       = the INACTIVE event's ``sistEndret`` (or its
  ``date_modified``). **This is the lab's first source-reported ``removed_at``**,
  so the MPSV-style cross-sweep reconciliation pass (``scrapers.reconcile_mpsv``)
  is **not** needed here — closures come straight from the source's own event.
- ``number_of_vacancies`` = ``int(ad_content.positioncount)``, which is a
  **string** at source (``"1"``, ``"2"``), with a safe default of 1.
- **Region:** ``workLocations[].county`` (fylke) -> ``mapped``, else
  ``workLocations[].municipal`` (kommune) -> ``mapped``, else
  ``_feed_entry.municipal`` -> ``low_confidence`` (a single denormalized header
  field that cannot be cross-checked against the ad's own ``workLocations`` and
  is the only region signal a content-masked ad has), all through the pinned
  ``data/reference/nav_region_nuts_2024.csv`` (SSB Klass x Eurostat GISCO NUTS
  2024). Locations that disagree -> ``ambiguous``; a workplace outside Norway ->
  ``unmapped``; a name the crosswalk does not know (the feed emits non-kommune
  strings such as ``"?"``) -> ``unmapped``; no name at all -> ``not_present``.
- **Occupation: mapped from the source's own ESCO URI — a first for this lab.**
  ``ad_content.categoryList`` carries three code systems on the same ad
  (``ESCO``, ``JANZZ``, ``STYRK08``); the ``ESCO`` entry's ``code`` *is* an ESCO
  occupation URI (``http://data.europa.eu/esco/occupation/<uuid>``), so
  ``esco_occupation_uri`` is populated directly with
  ``occupation_mapping_method="nav_categorylist_esco"`` and a confidence bucketed
  from the entry's ``score`` (see :func:`score_confidence`). Several ESCO entries
  -> the highest score wins, and a tie on the highest score is recorded as
  ``ambiguous``. ``esco_occupation_label`` stays **``None`` on purpose**: the
  source's ``categoryList[].name`` is Norwegian (``butikkmedarbeider``) while this
  project publishes **English** labels, and the pinned
  ``data/reference/jobtech_occupation_esco_1.2.1.csv`` is a JobTech->ESCO
  crosswalk with **Swedish** labels (3,891 rows), not the ESCO 1.2.1 occupation
  universe, so neither can supply an English label. The URI is the authoritative
  payload; the label is resolved downstream. ``JANZZ``/``STYRK08`` are occupation
  codes, not skills, so ``skill_mappings`` stays ``[]``.

PII and ToS compliance: the detail payload carries ``contactList``
(name/email/phone), ``employer`` (name/orgnr/description/homepage), a ~3.7 kB
free-text ``description``, ``title``/``jobtitle``, ``applicationUrl``,
``sourceurl``, ``link`` and ``workLocations[].address``/``city``/``postalCode``,
and the feed item itself adds ``title``, ``content_text``,
``_feed_entry.title`` and ``_feed_entry.businessName``. **None of them are
declared on the payload models** (``extra="ignore"``, so they never reach
:meth:`NAVFeedCollector.parse`), ``NormalizedRecord(extra="forbid")`` is the
backstop, and county/municipality names are read transiently to derive NUTS 3
and never persisted. This also satisfies the ToS obligations: inactive ads are
marked closed at the source's own timestamp (obligation 1), the daily poll keeps
rows current (obligation 2), and obligations 3-4 (ad display on the consumer's
domain, deep-linking the apply function) are N/A because this lab publishes no
ad listings and no apply links at all.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import unicodedata
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from typing import Any, ClassVar, Final

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

NAV_BASE = "https://pam-stilling-feed.nav.no"
NAV_ROBOTS_URL = f"{NAV_BASE}/robots.txt"
NAV_FEED_PATH = "/api/v1/feed"
NAV_FEED_URL = f"{NAV_BASE}{NAV_FEED_PATH}"
NAV_PUBLIC_TOKEN_URL = f"{NAV_BASE}/api/publicToken"
NAV_FEEDENTRY_PATH = "/api/v1/feedentry/{uuid}"

NAV_SOURCE_VERSION = "pam-stilling-feed-v1"
NAV_SCOPE_ID = "no-all-events"
#: Stable across daily sweeps: the window and the budgets are *not* part of the
#: scope (they belong in ``coverage_limitations``), so ``scope_hash`` does not
#: move when a poll uses a different ``--since``.
NAV_SCOPE_PARAMS: dict[str, str] = {
    "source": "nav",
    "country": "NO",
    "api": "pam-stilling-feed-v1",
    "query": "all-events",
    "segmentation": "none",
}
NAV_LICENCE_REFERENCE = "https://arbeidsplassen.nav.no/vilkar-api"
NAV_ACCESS_METHOD = "public-api"
#: ToS obligation 2: republished/derived ads must follow API updates; a daily
#: poll is the freshness target.
NAV_FRESHNESS_THRESHOLD_HOURS = 24

#: Charter floor; NAV documents no rate limit at all.
NAV_PACING_SECONDS = 1.0
#: Per-request timeout, deliberately above the lab's 30 s default: measured live
#: on 2026-08-23, ``/api/publicToken`` answered in **26-28 s** while the host was
#: degraded (and the feed briefly answered 500), which expired the 30 s default
#: mid-sweep. A slow public service is not a reason to hammer it, so the timeout
#: is widened and the token is cached instead.
NAV_REQUEST_TIMEOUT_SECONDS = 90.0
#: Items per feed page (fixed by the server; verified live).
NAV_ITEMS_PER_PAGE = 1000
#: Default backfill window when no cursor exists.
NAV_DEFAULT_SINCE_DAYS = 7
#: "an ad can never be active for more than 6 months" (NAV docs) — a longer
#: backfill only re-reads dead history.
NAV_MAX_SINCE_DAYS = 190
#: Detail requests per sweep. Each one is a paced request (~1 s), so this is the
#: sweep's wall-clock dial and the honest bound on ESCO/publication coverage.
NAV_DEFAULT_DETAIL_BUDGET = 1500
#: Feed pages per sweep when no explicit budget is given (1,000 events each).
NAV_DEFAULT_PAGE_BUDGET = 60

NAV_USER_AGENT = (
    "EU-Tech-Labour-Observatory/0.1 (+public job-data research, robots-and-ToS-compliant, "
    "arbeidsplassen.no API terms: statistical/analytical use)"
)

NAV_REFERENCE_FILE = "nav_region_nuts_2024.csv"
#: Poll cursor (gitignored by ``data/*``): the page to resume from plus its ETag.
NAV_CURSOR_FILE = Path("data/state/nav_feed_cursor.json")
#: Cache for NAV's **public** token (gitignored by ``data/*``). The token is
#: published at a public URL for anyone to use, and the endpoint is slow and
#: rotates only "at irregular intervals", so caching it locally means one request
#: per rotation instead of one per sweep — less load on NAV and no repeated waits.
#: A **private** consumer token is never written here: it comes from ``.env`` and
#: stays there. No token is ever committed (``data/*`` is gitignored) or logged.
NAV_TOKEN_CACHE_FILE = Path("data/state/nav_public_token.json")

NAV_COVERAGE_LIMITATIONS = (
    "Official Nav job-ad feed (arbeidsplassen.no). **The feed is an append-only "
    "event log, not a snapshot:** every change to an ad appends an entry and only "
    "the latest entry per ad uuid is written (folded on HMAC source_id), so a "
    "sweep is a window over the event stream and never a complete active-stock "
    "snapshot. Nav publishes no advertised active-ad total, so no completeness "
    "ratio is claimed. **Vacancies from Finn.no are documented by Nav as not "
    "included in this API.** The window is set by If-Modified-Since (--since "
    "days; ads are never active longer than ~6 months, so a longer backfill is "
    "pointless) and the number of feed pages by --max-pages at 1,000 events per "
    "page. **Ad details are budgeted:** each /api/v1/feedentry/<uuid> call is one "
    "paced request (>=1 s), so --max-details bounds how many rows carry "
    "first_published, positioncount, workLocations and the ESCO occupation URI; "
    "rows beyond the budget are written from the feed event alone (region from "
    "_feed_entry.municipal at low_confidence, occupation not_present). The budget "
    "is spent in HMAC source_id order, i.e. a deterministic sample spread across "
    "the whole window rather than the oldest N events. **INACTIVE details are "
    "never fetched:** measured live, only 2 of 20 still carried ad_content (Nav "
    "masks ads that are actively stopped rather than merely expired), so an "
    "INACTIVE row is written from its feed event, which already reports the "
    "closure timestamp. removed_at is therefore source-reported and needs no "
    "cross-sweep reconciliation. esco_occupation_label is deliberately null: the "
    "source's category name is Norwegian and this project publishes English "
    "labels, so only the ESCO URI is carried."
)

#: An ESCO 1.2.1 occupation URI, e.g.
#: ``http://data.europa.eu/esco/occupation/0b15375e-dfdd-4047-9efb-096e0aaee7d2``.
ESCO_OCCUPATION_URI: Final = re.compile(
    r"^http://data\.europa\.eu/esco/occupation/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
#: Some ads classify to an **ISCO-08 group** instead of an ESCO occupation, and
#: NAV still labels the entry ``categoryType: "ESCO"`` — measured live:
#: ``{"categoryType":"ESCO","code":"http://data.europa.eu/esco/isco/c9112",
#: "name":"Renholdsarbeider"}``. That is a different concept scheme (a 4-digit
#: aggregate group, not an occupation), so it is **never** written into
#: ``esco_occupation_uri``; it is reported ``unmapped`` with its own method name
#: so the reason stays visible instead of looking like a parse failure.
ESCO_ISCO_GROUP_URI: Final = re.compile(r"^http://data\.europa\.eu/esco/isco/[cC]?\d{1,4}$")

#: Values of ``workLocations[].country`` that mean Norway (the feed shouts
#: ``"NORGE"``); anything else non-empty is a foreign workplace.
NORWAY_COUNTRY_NAMES: Final[frozenset[str]] = frozenset({"norge", "norway", "no", "nor"})

#: SSB writes Sami dual names with a spaced hyphen (``"Nordland - Nordlånnda"``)
#: and GISCO with slashes (``"Troms/Romsa/Tromssa"``); kommune names use bare
#: hyphens inside a single name (``"Aurskog-Høland"``), which must survive.
_DUAL_NAME_SEPARATOR: Final = re.compile(r"\s+-\s+|/")
#: SSB disambiguates repeated municipality names with a parenthetical county
#: (``"Herøy (Møre og Romsdal)"``, ``"Våler (Østfold)"``). The feed sends the bare
#: name (``"HERØY"``), so the qualifier is dropped from the key — which is what
#: lets the builder *detect* the collision and mark the name ambiguous instead of
#: leaving two keys the feed can never hit.
_NAME_QUALIFIER: Final = re.compile(r"\([^)]*\)")
#: Letters ``unicodedata`` cannot decompose into base + combining mark.
_LETTER_FOLDING: Final[dict[str, str]] = {
    "ø": "o",
    "æ": "ae",
    "å": "a",
    "đ": "d",
    "ð": "d",
    "ŋ": "n",
    "ŧ": "t",
    "ß": "ss",
}
_NON_ALNUM: Final = re.compile(r"[^a-z0-9]+")


def normalize_region_name(value: str | None) -> str:
    """Fold a Norwegian place name to a join key shared by SSB, GISCO and the feed.

    The feed shouts names in upper case with Norwegian letters (``"TRØNDELAG"``,
    ``"MØRE OG ROMSDAL"``), SSB writes Sami dual names with a spaced hyphen
    (``"Troms - Romsa - Tromssa"``) and GISCO with slashes
    (``"Troms/Romsa/Tromssa"``), so only the **Norwegian part** is compared, and
    it is compared case-, accent- and punctuation-insensitively. Bare hyphens
    inside a single name (``"Aurskog-Høland"``, ``"Nord-Odal"``) are *not*
    separators and are preserved as word boundaries. SSB's disambiguating
    parenthetical (``"Herøy (Nordland)"``) is dropped, because the feed sends the
    bare name and the collision must surface as ``ambiguous`` rather than as two
    unreachable keys.

    The builder and the collector must use this one function, or the pinned
    crosswalk's keys and the live lookups would drift apart.
    """
    if not value:
        return ""
    unqualified = _NAME_QUALIFIER.sub(" ", value)
    head = _DUAL_NAME_SEPARATOR.split(unqualified.strip(), maxsplit=1)[0]
    folded = "".join(_LETTER_FOLDING.get(char, char) for char in head.casefold())
    decomposed = unicodedata.normalize("NFKD", folded)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _NON_ALNUM.sub(" ", stripped).strip()


def parse_nav_datetime(value: str | None) -> datetime | None:
    """Parse a NAV timestamp (``2026-08-21T09:46:01.790496+02:00``).

    Total by construction: an absent or unparseable value returns ``None``
    instead of a guess. A naive timestamp is assumed UTC.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def parse_position_count(value: str | int | float | None) -> int:
    """Coerce ``ad_content.positioncount`` (a **string** at source) to a count.

    ``"2"`` -> 2, ``"1"`` -> 1. Absent, empty or non-numeric values fall back to
    1 (one advertised vacancy is the only defensible default for a job ad), and
    negative values clamp to 0 because ``NormalizedRecord`` forbids them.
    """
    if value is None:
        return 1
    if isinstance(value, bool):  # pragma: no cover - defensive, JSON has no bools here
        return 1
    if isinstance(value, int | float):
        return max(0, int(value))
    text = value.strip()
    if not text:
        return 1
    try:
        return max(0, int(text))
    except ValueError:
        try:
            return max(0, int(float(text)))
        except ValueError:
            return 1


def http_date(value: datetime) -> str:
    """RFC 1123 date for ``If-Modified-Since`` (``Thu, 20 Aug 2026 21:41:51 GMT``).

    ``email.utils.format_datetime`` is used instead of ``strftime`` because
    ``%a``/``%b`` are locale-dependent and this header must always be English.
    """
    return format_datetime(value.astimezone(UTC), usegmt=True)


def score_confidence(score: float | None) -> str | None:
    """Bucket a ``categoryList`` score into the manifest's confidence vocabulary.

    NAV returns a float in ``[0, 1]`` (every ESCO entry in the live sample scored
    ``1.0``). The buckets are ``high`` (>= 0.9), ``medium`` (>= 0.6) and ``low``
    (below 0.6, including an explicit 0.0). A missing score yields ``None``,
    because SCRAPERS.md defines the field as "confidence when the source
    provides one" and inventing one would overstate the mapping.
    """
    if score is None:
        return None
    if score >= 0.9:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def nav_private_token() -> str | None:
    """A private consumer token from ``NAV_FEED_TOKEN`` (env or ``.env``), if any.

    Returns ``None`` when unset, in which case the collector falls back to the
    public experimentation token NAV publishes for this purpose. A private token
    requires registering as a consumer by e-mail to
    ``nav.team.arbeidsplassen@nav.no`` (identifier, contact e-mail, phone,
    contact person and written confirmation of the terms); see
    `SCRAPER_FEASIBILITY.md`. Tokens are never hardcoded and never logged.
    """
    value = os.environ.get("NAV_FEED_TOKEN") or read_dotenv_value("NAV_FEED_TOKEN")
    return value.strip() or None if value else None


def parse_public_token(body: str) -> str:
    """Extract the JWT from ``/api/publicToken``'s ``text/plain`` body.

    The body is ``"Current public token for Nav Job Vacancy Feed:\\n<JWT>"``, so
    the token is the last non-empty line. A body without a 3-segment JWT raises
    rather than sending a malformed ``Authorization`` header.
    """
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    token = lines[-1] if lines else ""
    if token.count(".") != 2 or not all(token.split(".")):
        raise RuntimeError(
            "NAV public token endpoint did not return a 3-segment JWT "
            f"(got {len(token)} characters)"
        )
    return token


# ---------------------------------------------------------------------------
# Source-native payload models (extra="ignore": PII fields never enter parse)
# ---------------------------------------------------------------------------


class NavFeedEntry(BaseModel):
    """``_feed_entry`` on a feed item: the ad's identity and current state.

    ``title`` and ``businessName`` are deliberately **not** declared, so the ad
    title and the employer name never enter the pipeline.
    """

    model_config = ConfigDict(extra="ignore")

    #: NAV's migration pseudocode references ``_feed_entry.id``, which does not
    #: exist in the payload; the field is ``uuid`` (verified live).
    uuid: str = Field(min_length=1)
    status: str | None = None
    municipal: str | None = None
    sistEndret: str | None = None


class NavFeedItem(BaseModel):
    """One feed event. ``id``, ``url``, ``title`` and ``content_text`` are ignored."""

    model_config = ConfigDict(extra="ignore")

    feed_entry: NavFeedEntry = Field(alias="_feed_entry")
    date_modified: str | None = None


class NavFeedPage(BaseModel):
    """One feed page. ``feed_url`` is the page's own stable relative URL."""

    model_config = ConfigDict(extra="ignore")

    items: list[NavFeedItem] = Field(default_factory=list)
    next_url: str | None = None
    next_id: str | None = None
    feed_url: str | None = None
    id: str | None = None


class NavWorkLocation(BaseModel):
    """A workplace location. ``address``, ``city`` and ``postalCode`` are not read."""

    model_config = ConfigDict(extra="ignore")

    country: str | None = None
    county: str | None = None
    municipal: str | None = None


class NavCategory(BaseModel):
    """One ``categoryList`` entry (ESCO / JANZZ / STYRK08).

    ``name`` and ``description`` are not declared: the name is a Norwegian label
    and this project publishes English labels.
    """

    model_config = ConfigDict(extra="ignore")

    categoryType: str | None = None
    code: str | None = None
    score: float | None = None


class NavAdContent(BaseModel):
    """The allowlist-relevant slice of ``ad_content``.

    Not declared, and therefore never parsed: ``title``, ``jobtitle``,
    ``description``, ``employer``, ``contactList``, ``applicationUrl``,
    ``sourceurl``, ``link``, ``expires``, ``applicationDue``, ``starttime``,
    ``engagementtype``, ``extent``, ``sector``, ``occupationCategories``,
    ``source`` and ``uuid``.
    """

    model_config = ConfigDict(extra="ignore")

    published: str | None = None
    updated: str | None = None
    #: A **string** at source (``"2"``); ints are tolerated defensively.
    positioncount: str | int | float | None = None
    workLocations: list[NavWorkLocation] = Field(default_factory=list)
    categoryList: list[NavCategory] = Field(default_factory=list)


class NavFeedDetail(BaseModel):
    """``/api/v1/feedentry/<uuid>``. ``ad_content`` is absent on masked ads."""

    model_config = ConfigDict(extra="ignore")

    status: str | None = None
    sistEndret: str | None = None
    ad_content: NavAdContent | None = None


class FeedCursor(BaseModel):
    """Poll state: the page to resume from, its ETag and its successor.

    Persisted to :data:`NAV_CURSOR_FILE` so the next daily poll resumes instead
    of re-walking the window. ``page_url`` is the page's own ``feed_url``
    (a stable page id), never the bare ``/api/v1/feed`` seek URL, because the
    seek URL without ``If-Modified-Since`` restarts at 2019.
    """

    model_config = ConfigDict(extra="ignore")

    page_url: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    next_url: str | None = None
    sweep_id: str | None = None
    updated_at: str | None = None
    events_seen: int | None = None


def load_cursor(path: Path = NAV_CURSOR_FILE) -> FeedCursor | None:
    """Read the poll cursor, or ``None`` when absent or unreadable."""
    if not path.exists():
        return None
    try:
        return FeedCursor.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def save_cursor(cursor: FeedCursor, path: Path = NAV_CURSOR_FILE) -> None:
    """Persist the poll cursor (creating ``data/state/`` when needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cursor.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_cached_token(path: Path = NAV_TOKEN_CACHE_FILE) -> str | None:
    """Read the cached **public** token, or ``None`` when absent or malformed.

    Only a well-formed 3-segment JWT is returned, so a truncated cache file makes
    the collector fetch a fresh token instead of sending a broken header.
    """
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or token.count(".") != 2 or not all(token.split(".")):
        return None
    return token


def save_cached_token(token: str, path: Path = NAV_TOKEN_CACHE_FILE) -> None:
    """Cache the public token in gitignored local state (never in git, never logged)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"token": token, "fetched_at": datetime.now(UTC).isoformat(), "source": "publicToken"},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Region crosswalk (NUTS 2024)
# ---------------------------------------------------------------------------


class RegionResolution(BaseModel):
    """Outcome of the name -> NUTS 2024 resolution for one ad."""

    nuts_code: str | None = None
    nuts_label: str | None = None
    status: MappingStatus = "unmapped"
    method: str = "not_available"


class OccupationResolution(BaseModel):
    """Outcome of the ``categoryList`` -> ESCO 1.2.1 resolution for one ad."""

    uri: str | None = None
    status: MappingStatus = "not_present"
    confidence: str | None = None
    method: str = "not_available"


#: ``source_type`` values in the pinned crosswalk.
FYLKE_KEY = "fylke"
KOMMUNE_KEY = "kommune"
#: A kommune name that occurs in more than one fylke (and therefore in more than
#: one NUTS 3 region) is written with this type and no code: it can never be
#: resolved from a name alone, so it is reported ``ambiguous`` rather than guessed.
KOMMUNE_AMBIGUOUS_KEY = "kommune-ambiguous"


class NAVCrosswalk:
    """Loads the pinned fylke/kommune name -> NUTS 2024 table and resolves regions.

    Keys are :func:`normalize_region_name` outputs, so the same folding applies
    to SSB's names, GISCO's names and the feed's shouted names.
    """

    def __init__(self, reference_dir: Path) -> None:
        path = reference_dir / NAV_REFERENCE_FILE
        if not path.exists():
            raise FileNotFoundError(
                f"missing NAV crosswalk reference: {path} "
                "(rebuild with `python -m scrapers.reference_nav`)"
            )
        self._fylke: dict[str, tuple[str, str]] = {}
        self._kommune: dict[str, tuple[str, str]] = {}
        self._ambiguous: set[str] = set()
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                key = (row.get("source_code") or "").strip()
                if not key:
                    continue
                value = (
                    (row.get("nuts_code") or "").strip(),
                    (row.get("nuts_label") or "").strip(),
                )
                source_type = (row.get("source_type") or "").strip()
                if source_type == FYLKE_KEY:
                    self._fylke[key] = value
                elif source_type == KOMMUNE_KEY:
                    self._kommune[key] = value
                elif source_type == KOMMUNE_AMBIGUOUS_KEY:
                    self._ambiguous.add(key)
        if not self._fylke and not self._kommune:
            raise ValueError(f"NAV crosswalk reference is empty: {path}")

    def fylker(self) -> list[str]:
        """The fylke keys the crosswalk knows (sorted, stable)."""
        return sorted(self._fylke)

    def kommuner(self) -> list[str]:
        """The kommune keys the crosswalk knows (sorted, stable)."""
        return sorted(self._kommune)

    def lookup_fylke(self, name: str | None) -> tuple[str, str] | None:
        return self._fylke.get(normalize_region_name(name))

    def lookup_kommune(self, name: str | None) -> tuple[str, str] | None:
        return self._kommune.get(normalize_region_name(name))

    def kommune_is_ambiguous(self, name: str | None) -> bool:
        """True when the name occurs in more than one fylke (e.g. two ``Herøy``)."""
        key = normalize_region_name(name)
        return bool(key) and key in self._ambiguous

    def _resolve_names(
        self,
        names: Sequence[str | None],
        *,
        lookup: str,
        method: str,
        status: MappingStatus,
    ) -> RegionResolution | None:
        """Resolve one axis (fylke or kommune) across an ad's locations."""
        hits: dict[str, str] = {}
        ambiguous_name = False
        for name in names:
            if lookup == FYLKE_KEY:
                hit = self.lookup_fylke(name)
            else:
                hit = self.lookup_kommune(name)
                ambiguous_name = ambiguous_name or self.kommune_is_ambiguous(name)
            if hit is not None and hit[0]:
                hits[hit[0]] = hit[1]
        if not hits:
            # A name that is known to sit in several fylker resolves to no single
            # NUTS 3 code: report the ambiguity instead of picking one.
            return RegionResolution(status="ambiguous", method=method) if ambiguous_name else None
        code = sorted(hits)[0]
        return RegionResolution(
            nuts_code=code,
            nuts_label=hits[code],
            status="ambiguous" if len(hits) > 1 or ambiguous_name else status,
            method=method,
        )

    def resolve(
        self,
        *,
        locations: Sequence[NavWorkLocation] = (),
        feed_municipal: str | None = None,
    ) -> RegionResolution:
        """Resolve the region, first hit wins.

        1. ``workLocations[].county`` (fylke) -> ``mapped``
        2. ``workLocations[].municipal`` (kommune) -> ``mapped``
        3. ``_feed_entry.municipal`` -> ``low_confidence`` (a single denormalized
           header field, the only signal a content-masked ad has)
        4. a workplace outside Norway -> ``unmapped``
        5. a value present but not a known place -> ``unmapped``. This deliberately
           includes NAV's own ``"?"`` placeholder (measured live: 23 occurrences on
           one page): the source did emit a municipality field, it just does not
           name a municipality, and that is different from emitting nothing.
        6. no value at all -> ``not_present``

        Locations resolving to different NUTS 3 codes yield ``ambiguous``.
        """
        counties = [location.county for location in locations]
        municipals = [location.municipal for location in locations]
        resolved = self._resolve_names(
            counties,
            lookup=FYLKE_KEY,
            method="nav_worklocation_county_nuts3",
            status="mapped",
        )
        if resolved is not None:
            return resolved
        resolved = self._resolve_names(
            municipals,
            lookup=KOMMUNE_KEY,
            method="nav_worklocation_municipal_nuts3",
            status="mapped",
        )
        if resolved is not None:
            return resolved
        resolved = self._resolve_names(
            [feed_municipal],
            lookup=KOMMUNE_KEY,
            method="nav_feed_entry_municipal_nuts3",
            status="low_confidence",
        )
        if resolved is not None:
            return resolved
        countries = [normalize_region_name(location.country) for location in locations]
        named_countries = [country for country in countries if country]
        if named_countries and not any(
            country in NORWAY_COUNTRY_NAMES for country in named_countries
        ):
            return RegionResolution(status="unmapped", method="nav_worklocation_foreign_country")
        signals = [*counties, *municipals, feed_municipal]
        if any((signal or "").strip() for signal in signals):
            return RegionResolution(status="unmapped", method="nav_region_name_unknown")
        return RegionResolution(status="not_present", method="not_available")


def resolve_occupation(categories: Iterable[NavCategory]) -> OccupationResolution:
    """Pick the ESCO occupation URI from ``categoryList``.

    The highest ``score`` wins; a tie on the highest score is ``ambiguous`` (the
    lowest URI is still reported so the row stays usable).

    An ``ESCO`` entry whose ``code`` is not an ESCO **occupation** URI yields
    ``unmapped`` — the source offered an occupation code that this field cannot
    carry, which is different from offering none at all (``not_present``). Two
    such cases are distinguished by method name because they mean different
    things: an **ISCO-08 group** URI (``esco/isco/c9112``, measured live on ~15%
    of enriched ads) is a valid but coarser concept scheme, while anything else
    is unrecognized. ``JANZZ``/``STYRK08`` entries are occupation codes for other
    taxonomies and are ignored here; they are not skills, so ``skill_mappings``
    stays empty.
    """
    esco = [
        category
        for category in categories
        if (category.categoryType or "").strip().upper() == "ESCO"
    ]
    valid = [
        category
        for category in esco
        if category.code and ESCO_OCCUPATION_URI.match(category.code.strip())
    ]
    if not valid:
        codes = [(category.code or "").strip() for category in esco]
        if any(ESCO_ISCO_GROUP_URI.match(code) for code in codes):
            return OccupationResolution(
                status="unmapped", method="nav_categorylist_esco_isco_group"
            )
        if esco:
            return OccupationResolution(
                status="unmapped", method="nav_categorylist_esco_unrecognized"
            )
        return OccupationResolution(status="not_present", method="not_available")
    best = max((category.score if category.score is not None else 0.0) for category in valid)
    winners = sorted(
        {
            (category.code or "").strip()
            for category in valid
            if (category.score if category.score is not None else 0.0) >= best
        }
    )
    scores = [category.score for category in valid if (category.code or "").strip() == winners[0]]
    return OccupationResolution(
        uri=winners[0],
        status="ambiguous" if len(winners) > 1 else "mapped",
        confidence=score_confidence(scores[0] if scores else None),
        method="nav_categorylist_esco",
    )


def crosswalk_reference_hashes(reference_dir: Path) -> str:
    """SHA-256 of the pinned crosswalk CSV (content only)."""
    digest = hashlib.sha256()
    with (reference_dir / NAV_REFERENCE_FILE).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return f"{NAV_REFERENCE_FILE}:{digest.hexdigest()}"


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class FoldedEvent(BaseModel):
    """The latest feed event seen for one ad uuid (the fold's value).

    The fold is keyed on the HMAC ``source_id``; this record keeps the native
    ``uuid`` only so the detail endpoint can be called.
    """

    model_config = ConfigDict(extra="forbid")

    uuid: str
    status: str | None = None
    sist_endret: str | None = None
    date_modified: str | None = None
    feed_municipal: str | None = None
    events: int = 1


class NAVFeedCollector(BaseCollector):
    """Collector for NAV's pam-stilling-feed (Norway).

    Walks the feed from an ``If-Modified-Since`` window (or resumes from the
    persisted cursor), folds the append-only event log to one row per ad uuid,
    enriches a budgeted subset with the ad detail (ACTIVE only), and maps the
    source's own ESCO URI onto the allowlist.
    """

    source: ClassVar[str] = "nav"
    country: ClassVar[str] = "NO"

    def __init__(
        self,
        *,
        scope_id: str,
        sweep_id: str,
        observed_at: datetime,
        hmac_key: bytes,
        reference_dir: Path = Path("data/reference"),
        since_days: int | None = None,
        max_pages: int | None = None,
        max_details: int | None = None,
        token: str | None = None,
        cursor_path: Path | None = NAV_CURSOR_FILE,
        token_cache_path: Path | None = NAV_TOKEN_CACHE_FILE,
        use_cursor: bool = True,
        pacing_interval: float = NAV_PACING_SECONDS,
        policy: RetryPolicy | None = None,
        timeout: float = NAV_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            scope_id=scope_id, sweep_id=sweep_id, observed_at=observed_at, timeout=timeout
        )
        if len(hmac_key) < 32:
            raise ValueError("hmac_key must be at least 32 bytes")
        self._hmac_key = hmac_key
        self._crosswalk = NAVCrosswalk(reference_dir)
        self._since_days = min(
            NAV_MAX_SINCE_DAYS,
            max(1, since_days if since_days is not None else NAV_DEFAULT_SINCE_DAYS),
        )
        self._explicit_since = since_days is not None
        self._page_budget = NAV_DEFAULT_PAGE_BUDGET if max_pages is None else max(1, max_pages)
        #: Ad-detail requests allowed this sweep (public: the manifest reports it).
        self.detail_budget = (
            NAV_DEFAULT_DETAIL_BUDGET if max_details is None else max(0, max_details)
        )
        self._token = token
        self._cursor_path = cursor_path
        self._token_cache_path = token_cache_path
        self._use_cursor = use_cursor
        self._policy = policy or RetryPolicy()
        self._pacer = PacingGate(min_interval=pacing_interval)
        self._pacing_interval = pacing_interval
        self._robots: RobotsRule | None = None
        self._headers = {"User-Agent": NAV_USER_AGENT, "Accept": "application/json"}
        self.total_elements = 0
        self.total_pages = 0
        self.completed_pages = 0
        #: Token endpoint calls (0 when a private NAV_FEED_TOKEN is configured).
        self.token_requests = 0
        #: 401s that triggered a refresh-and-replay (token rotation).
        self.token_refreshes = 0
        #: Feed events read before folding.
        self.events_seen = 0
        #: Feed pages that answered 304 Not Modified (nothing new).
        self.pages_unchanged = 0
        #: Detail requests actually made, and their outcomes.
        self.detail_requests = 0
        self.details_with_content = 0
        self.details_masked = 0
        self.details_missing = 0
        #: Details abandoned after retries because NAV answered 5xx (skipped, not fatal).
        self.details_failed = 0
        #: Folded rows by feed status.
        self.rows_active = 0
        self.rows_inactive = 0
        #: Rows carrying a source-reported removed_at.
        self.rows_removed = 0
        #: Rows carrying an ESCO occupation URI.
        self.rows_with_esco = 0
        #: True when the sweep resumed from the persisted cursor.
        self.resumed_from_cursor = False
        #: The window actually requested (None when resuming from the cursor).
        self.since_header: str | None = None
        self._cursor: FeedCursor | None = None

    # -- robots gate --------------------------------------------------------

    async def _load_robots(self) -> RobotsRule:
        """Fetch and parse ``robots.txt`` once per sweep, before any other URL.

        NAV's feed host answers 404 (a Javalin JSON error body), i.e. the file is
        absent and nothing is disallowed. It is fetched anyway because the
        charter requires the check, and a future robots file is honored
        automatically.
        """
        if self._robots is not None:
            return self._robots

        async def do_get() -> httpx.Response:
            return await self._client.get(NAV_ROBOTS_URL, headers=self._headers)

        await self._pacer.wait()
        response = await with_backoff(self._policy)(do_get)()
        served = response.status_code == 200 and "text/plain" in (
            response.headers.get("content-type") or ""
        )
        rule = RobotsRule(response.text if served else None)
        self._robots = rule
        delay = rule.crawl_delay(NAV_USER_AGENT)
        self._log.info(
            "nav_robots_loaded",
            status=response.status_code,
            served=served,
            bytes=len(response.content),
            crawl_delay=delay,
            feed_allowed=rule.can_fetch(NAV_FEED_URL, NAV_USER_AGENT),
        )
        if delay is not None and delay > self._pacing_interval:
            self._pacer = PacingGate(min_interval=delay)
        return rule

    def assert_allowed(self, url: str) -> None:
        """Raise :class:`RobotsDisallowedError` unless robots.txt permits ``url``."""
        rule = self._robots
        if rule is None:
            raise RobotsDisallowedError(f"robots.txt not loaded before requesting {url}")
        if not rule.can_fetch(url, NAV_USER_AGENT):
            raise RobotsDisallowedError(f"robots.txt disallows {url} for {NAV_USER_AGENT}")

    # -- auth ---------------------------------------------------------------

    async def _fetch_public_token(self) -> str:
        """Fetch NAV's public experimentation token (paced and retried)."""

        async def do_get() -> httpx.Response:
            return await self._client.get(
                NAV_PUBLIC_TOKEN_URL, headers={"User-Agent": NAV_USER_AGENT}
            )

        self.assert_allowed(NAV_PUBLIC_TOKEN_URL)
        await self._pacer.wait()
        response = await with_backoff(self._policy)(do_get)()
        self.token_requests += 1
        if response.status_code != 200:
            response.raise_for_status()
        token = parse_public_token(response.text)
        self._log.info(
            "nav_public_token_fetched",
            token_requests=self.token_requests,
            token_length=len(token),
            segments=token.count(".") + 1,
        )
        return token

    async def _access_token(self, *, force: bool = False) -> str:
        """Return a live bearer token, refreshing only when asked to.

        Order: a configured ``NAV_FEED_TOKEN`` (private consumer token) wins;
        otherwise the cached public token is reused; otherwise it is fetched and
        cached. ``force`` (a 401 mid-sweep, i.e. NAV's documented irregular
        rotation) bypasses both the in-memory and the on-disk copy.
        """
        if self._token is not None and not force:
            return self._token
        private = nav_private_token()
        if private:
            self._token = private
            return private
        if not force and self._token_cache_path is not None:
            cached = load_cached_token(self._token_cache_path)
            if cached:
                self._token = cached
                self._log.info("nav_public_token_from_cache", token_length=len(cached))
                return cached
        token = await self._fetch_public_token()
        self._token = token
        if self._token_cache_path is not None:
            save_cached_token(token, self._token_cache_path)
        return token

    # -- HTTP ---------------------------------------------------------------

    async def _get(self, url: str, headers: Mapping[str, str]) -> httpx.Response:
        """One paced, retried, robots-checked GET."""
        self.assert_allowed(url)

        async def do_get() -> httpx.Response:
            return await self._client.get(url, headers={**self._headers, **headers})

        await self._pacer.wait()
        return await with_backoff(self._policy)(do_get)()

    async def _get_authorized(self, url: str, conditional: Mapping[str, str]) -> httpx.Response:
        """GET with a bearer token, refreshing once and replaying on a 401.

        The public token "will rotate at irregular intervals", so a 401 in the
        middle of a sweep is expected operation, not a failure: the token is
        re-read (or re-fetched) once and the identical request is replayed. A
        second 401 is a real error and is raised by the caller.
        """
        token = await self._access_token()
        response = await self._get(url, {**conditional, "Authorization": f"Bearer {token}"})
        if response.status_code == 401:
            self.token_refreshes += 1
            self._log.info("nav_token_rotated_refreshing", url=url, refreshes=self.token_refreshes)
            token = await self._access_token(force=True)
            response = await self._get(url, {**conditional, "Authorization": f"Bearer {token}"})
        return response

    # -- feed walk ----------------------------------------------------------

    def _start(self) -> tuple[str, dict[str, str]]:
        """The first URL of the walk plus its conditional headers.

        Resumes from the cursor when one exists (and ``--since`` was not given
        explicitly): the cursor's ``next_url`` if the previous sweep stopped
        mid-feed, otherwise the cursor's own page revalidated with
        ``If-None-Match`` — which is how NAV expects a consumer to poll the tail.
        Falls back to a seek with ``If-Modified-Since``.
        """
        cursor = self._cursor
        if cursor is not None and not self._explicit_since:
            if cursor.next_url:
                self.resumed_from_cursor = True
                return f"{NAV_BASE}{cursor.next_url}", {}
            if cursor.page_url:
                self.resumed_from_cursor = True
                conditional = {"If-None-Match": cursor.etag} if cursor.etag else {}
                return f"{NAV_BASE}{cursor.page_url}", conditional
        since = self.observed_at - timedelta(days=self._since_days)
        self.since_header = http_date(since)
        return NAV_FEED_URL, {"If-Modified-Since": self.since_header}

    async def _walk_feed(self) -> dict[str, FoldedEvent]:
        """Walk pages from the start position, folding events per ad uuid.

        Last event wins: NAV documents that "each change to an ad will generate a
        new entry in the feed, and the latest entry will contain the current
        state of the ad", and pages are appended in chronological order.
        """
        folded: dict[str, FoldedEvent] = {}
        url, conditional = self._start()
        cursor = FeedCursor(sweep_id=self.sweep_id, updated_at=self.observed_at.isoformat())
        while url and self.completed_pages < self._page_budget:
            response = await self._get_authorized(url, conditional)
            conditional = {}
            if response.status_code == 304:
                # "Unchanged", not an error: the tail has no new events yet.
                self.completed_pages += 1
                self.pages_unchanged += 1
                self._log.info("nav_page_unchanged", url=url)
                cursor = self._cursor or cursor
                break
            if response.status_code != 200:
                response.raise_for_status()
            page = NavFeedPage.model_validate(response.json())
            self.completed_pages += 1
            requested_path = url[len(NAV_BASE) :] if url.startswith(NAV_BASE) else url
            cursor = FeedCursor(
                page_url=page.feed_url or requested_path,
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
                next_url=page.next_url,
                sweep_id=self.sweep_id,
                updated_at=self.observed_at.isoformat(),
                events_seen=self.events_seen + len(page.items),
            )
            for item in page.items:
                entry = item.feed_entry
                source_id = pseudonymize(entry.uuid, self._hmac_key)
                previous = folded.get(source_id)
                folded[source_id] = FoldedEvent(
                    uuid=entry.uuid,
                    status=entry.status,
                    sist_endret=entry.sistEndret,
                    date_modified=item.date_modified,
                    feed_municipal=entry.municipal,
                    events=(previous.events + 1) if previous else 1,
                )
                self.events_seen += 1
            self._log.info(
                "nav_feed_page",
                page=self.completed_pages,
                items=len(page.items),
                events_seen=self.events_seen,
                folded=len(folded),
                end_of_feed=page.next_url is None and page.next_id is None,
            )
            if page.next_url is None or page.next_id is None:
                break
            url = f"{NAV_BASE}{page.next_url}"
        if self._cursor_path is not None:
            save_cursor(cursor, self._cursor_path)
        return folded

    # -- details ------------------------------------------------------------

    async def _fetch_detail(self, uuid: str) -> NavFeedDetail | None:
        """One ad detail, or ``None`` when NAV cannot serve it.

        Details are **optional enrichment**: the row is written from the feed
        event either way, and the detail budget already means most rows carry
        none. So a 404 (no longer served) or a persistent 5xx is counted and
        skipped rather than aborting a sweep that has already collected
        thousands of rows — measured on 2026-08-23, the host intermittently
        answered 500 and timed out. A **feed page** failure stays fatal, because
        a lost page is lost events; a non-404 4xx also stays fatal, because that
        is a permission signal worth stopping for.
        """
        url = f"{NAV_BASE}{NAV_FEEDENTRY_PATH.format(uuid=uuid)}"
        response = await self._get_authorized(url, {})
        self.detail_requests += 1
        if response.status_code == 404:
            self.details_missing += 1
            return None
        if response.status_code >= 500:
            self.details_failed += 1
            self._log.warning("nav_detail_failed", status=response.status_code)
            return None
        if response.status_code != 200:
            response.raise_for_status()
        detail = NavFeedDetail.model_validate(response.json())
        if detail.ad_content is None:
            # Actively stopped ads are content-masked (measured: 18 of 20).
            self.details_masked += 1
        else:
            self.details_with_content += 1
        return detail

    def _wants_detail(self, event: FoldedEvent) -> bool:
        """Only ACTIVE ads are worth a paced detail request.

        Measured live: just 2 of 20 INACTIVE details still carried
        ``ad_content``, and an INACTIVE row already has its closure timestamp and
        its municipality on the feed event, so the other 18 requests would buy
        nothing.
        """
        return (event.status or "").strip().upper() == "ACTIVE"

    # -- fetch --------------------------------------------------------------

    def fetch(self) -> AsyncIterator[RawRecord]:
        """Walk the feed, fold it, then yield one RawRecord per ad uuid."""
        return self._fetch()

    async def _fetch(self) -> AsyncIterator[RawRecord]:
        await self._load_robots()
        if self._use_cursor and self._cursor_path is not None:
            self._cursor = load_cursor(self._cursor_path)
        folded = await self._walk_feed()

        rows = 0
        for source_id in sorted(folded):
            # HMAC order: a deterministic sample spread across the whole window,
            # so a partial detail budget is not biased towards the oldest events.
            event = folded[source_id]
            detail: NavFeedDetail | None = None
            if self._wants_detail(event) and self.detail_requests < self.detail_budget:
                detail = await self._fetch_detail(event.uuid)
            rows += 1
            yield RawRecord(
                native_id=event.uuid,
                payload={
                    "status": event.status,
                    "sist_endret": event.sist_endret,
                    "date_modified": event.date_modified,
                    "feed_municipal": event.feed_municipal,
                    "events": event.events,
                    # Model dumps only: the raw JSON (employer, contacts,
                    # description, URLs) never enters the pipeline.
                    "detail": detail.model_dump() if detail is not None else None,
                },
            )

        self.total_pages = self.completed_pages
        self.total_elements = rows
        self._log.info(
            "nav_sweep_summary",
            pages=self.completed_pages,
            pages_unchanged=self.pages_unchanged,
            events=self.events_seen,
            rows=rows,
            detail_requests=self.detail_requests,
            details_masked=self.details_masked,
            token_requests=self.token_requests,
            token_refreshes=self.token_refreshes,
        )

    # -- normalization ------------------------------------------------------

    def parse(self, raw: RawRecord) -> dict[str, Any]:
        """Extract the source-native fields the allowlist needs from one row."""
        payload = raw.payload
        detail_payload = payload.get("detail")
        detail = (
            NavFeedDetail.model_validate(detail_payload)
            if isinstance(detail_payload, dict)
            else None
        )
        content = detail.ad_content if detail is not None else None
        status = (payload.get("status") or "").strip().upper()
        sist_endret = payload.get("sist_endret")
        date_modified = payload.get("date_modified")
        return {
            "native_id": raw.native_id,
            "status": status,
            "first_published": parse_nav_datetime(content.published if content else None),
            "last_modified": parse_nav_datetime(
                (content.updated if content else None) or sist_endret or date_modified
            ),
            "removed_at": (
                parse_nav_datetime(sist_endret or date_modified) if status == "INACTIVE" else None
            ),
            "number_of_vacancies": parse_position_count(content.positioncount if content else None),
            "locations": list(content.workLocations) if content else [],
            "categories": list(content.categoryList) if content else [],
            "feed_municipal": payload.get("feed_municipal"),
        }

    def normalize(self, parsed: dict[str, Any]) -> NormalizedRecord:
        """Map parsed fields onto the SAFE_FIELDS allowlist and pseudonymize the id."""
        region = self._crosswalk.resolve(
            locations=parsed["locations"], feed_municipal=parsed["feed_municipal"]
        )
        occupation = resolve_occupation(parsed["categories"])
        if parsed["status"] == "INACTIVE":
            self.rows_inactive += 1
        elif parsed["status"] == "ACTIVE":
            self.rows_active += 1
        if parsed["removed_at"] is not None:
            self.rows_removed += 1
        if occupation.uri is not None:
            self.rows_with_esco += 1
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
            source_language="no",
            jobtech_taxonomy_version="",
            esco_version="1.2.1",
            skill_mappings=[],
            lang="no",
            number_of_vacancies=parsed["number_of_vacancies"],
        )
