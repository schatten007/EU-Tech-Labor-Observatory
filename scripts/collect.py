"""Collect recorded or live JobTech observations into immutable partitions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import monotonic
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.enrich import ReferenceTables, enrich_hit, load_references, reference_provenance
from scripts.sanitize import key_from_env, sanitize_record

ROOT = Path(__file__).resolve().parents[1]
JOBTECH_SEARCH = "https://jobsearch.api.jobtechdev.se/search"
USER_AGENT = "eu-tech-labour-observatory/0.1 (non-commercial research; +see repo README)"
DEFAULT_QUERY = "utvecklare"
DEFAULT_PAGE_SIZE = 100
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_RETRY_DEADLINE_S = 120.0
DEFAULT_PAUSE_S = 0.5
COLLECTOR_VERSION = "0.3.0"
SCHEMA_VERSION = 3
JOBTECH_SOURCE_VERSION = "JobSearch current ads"
JOBTECH_LICENCE_REFERENCE = "https://data.jobtechdev.se/dataservice/jobsearch/"
JOBTECH_ACCESS_METHOD = "official-public-api"
JOBTECH_APPROVAL_STATUS = "approved"
JOBTECH_EXPECTED_COUNTRY = "SE"
# ponytail: JobTech publishes SCB country codes, not ISO 3166, and 199 is Sverige. The same code
# filters the search server-side, so the handful of foreign ads that match a Swedish keyword never
# reach an approved Sweden-only sweep instead of aborting it mid-collection.
JOBTECH_SWEDEN_COUNTRY_CODE = "199"
# JobTech's own Data/IT classification: 2,574 ads against the keyword scope's 624. It is a second
# scope, never a replacement. Scope definitions are append-only, because an abandoned scope's
# postings can never be closed and would keep rendering as active forever.
JOBTECH_DATA_IT_FIELD = "apaJ_2ja_LuF"
JOBTECH_FRESHNESS_THRESHOLD_HOURS = 48
JOBTECH_COVERAGE_LIMITATIONS = (
    "Keyword-scoped Platsbanken postings filtered to Sweden; provider-default ordering is not "
    "a transactional snapshot."
)
JOBTECH_OCCUPATION_FIELD_LIMITATIONS = (
    "Occupation-field-scoped Platsbanken postings filtered to Sweden; the source's own field "
    "filter admits a few percent of adjacent occupations from other fields, and provider-default "
    "ordering is not a transactional snapshot."
)
# The field filter is the source's, not an equality test on the field each ad reports: 97-100% of
# a page matches and the rest are adjacent occupations the source counts as part of the query (a
# Säkerhetsingenjör answers a Data/IT search). An ignored parameter looks nothing like that: the
# misspelled camelCase name returned all 40,649 Swedish ads, of which Data/IT is 6%. A simple
# majority separates the two with room to spare, and never aborts a sweep that was really
# filtered — but only on a page large enough for the ratio to mean anything. On a two-row final
# page one adjacent hit is exactly 50%, and because the failed checkpoint is resumable the sweep
# would re-request that same page and refuse again, so a valid scope could never finish.
JOBTECH_FILTER_MAJORITY_SHARE = 0.5
JOBTECH_FILTER_MIN_SAMPLE = 10
# Measured: the search API answers any offset above 2000 with HTTP 400, whatever the limit
# (limit=1&offset=2099 is a 400; limit=100&offset=2000 is fine). So one query can never return
# more than 2000 + page_size records, however many it reports as its total.
JOBTECH_MAX_OFFSET = 2000
# Concept ids are a fixed shape (apaJ_2ja_LuF, E7hm_BLq_fqZ, DJh5_yyF_hEM). Checking it offline is
# the only defence against a typo, because a scope is append-only: a misspelled field the API
# answers with zero hits publishes a complete, empty partition under a brand-new scope_hash, and
# an empty page is exactly the case the filter guard cannot verify. That scope would then render
# forever and could never be closed.
JOBTECH_CONCEPT_ID = re.compile(r"[A-Za-z0-9]{4}_[A-Za-z0-9]{3}_[A-Za-z0-9]{3}")


class PageTransport(Protocol):
    def __call__(self, url: str, timeout: float) -> dict[str, Any]: ...


class CollectionError(RuntimeError):
    """A collection failed and its state manifest should remain inspectable."""


class TransientTransportError(CollectionError):
    """A connection-level failure that may be retried."""


@dataclass(frozen=True)
class RetryPolicy:
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    deadline_s: float = DEFAULT_RETRY_DEADLINE_S
    pause_s: float = DEFAULT_PAUSE_S
    backoff_s: float = 1.0
    max_backoff_s: float = 30.0
    jitter_s: float = 0.25


DEFAULT_RETRY_POLICY = RetryPolicy()


def _utc(value: str | datetime) -> datetime:
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _iso(value: str | datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _filename_timestamp(value: str | datetime) -> str:
    return _utc(value).strftime("%Y%m%dT%H%M%SZ")


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _selector(query: str | None, occupation_field: str | None) -> tuple[str | None, str | None]:
    """Reduce the two scope selectors to exactly one, defaulting to the keyword query."""
    if query is not None and occupation_field is not None:
        raise ValueError("a scope is either a query or an occupation field, not both")
    if occupation_field is not None and not JOBTECH_CONCEPT_ID.fullmatch(occupation_field):
        raise ValueError("occupation field must be a JobTech concept id, e.g. apaJ_2ja_LuF")
    if query is None and occupation_field is None:
        return DEFAULT_QUERY, None
    return query, occupation_field


def _search_params(
    query: str | None, page_size: int, occupation_field: str | None
) -> dict[str, Any]:
    """The one request a sweep sends, so the recorded scope cannot drift from the wire."""
    if (query is None) == (occupation_field is None):
        raise ValueError("search params need exactly one of query or occupation field")
    chosen = {"q": query} if query is not None else {"occupation-field": occupation_field}
    return {**chosen, "limit": page_size, "country": JOBTECH_SWEDEN_COUNTRY_CODE}


def _coverage_limitations(occupation_field: str | None) -> str:
    """Provenance must name the scope it describes; a Data/IT sweep is not keyword-scoped."""
    if occupation_field is None:
        return JOBTECH_COVERAGE_LIMITATIONS
    return JOBTECH_OCCUPATION_FIELD_LIMITATIONS


def _scope(query: str | None, page_size: int, occupation_field: str | None) -> tuple[str, str, str]:
    scope = {
        "endpoint": JOBTECH_SEARCH,
        "params": _search_params(query, page_size, occupation_field),
        "ordering": "provider-default",
        "country": JOBTECH_EXPECTED_COUNTRY,
        "language": "sv",
        "collector_version": COLLECTOR_VERSION,
    }
    scope_json = _canonical_json(scope)
    scope_hash = hashlib.sha256(scope_json.encode()).hexdigest()
    return f"jobtech-{scope_hash[:16]}", scope_hash, scope_json


def collection_scope(
    query: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    occupation_field: str | None = None,
) -> tuple[str, str, str]:
    """Return the stable identifier, hash, and canonical JSON for a sweep scope."""
    resolved_query, resolved_field = _selector(query, occupation_field)
    return _scope(resolved_query, page_size, resolved_field)


def _key_version(key: bytes) -> str:
    del key
    label = os.environ.get("OBSERVATORY_HMAC_KEY_VERSION", "v1")
    if not label.replace("-", "").replace("_", "").isalnum():
        raise ValueError("OBSERVATORY_HMAC_KEY_VERSION contains unsafe characters")
    return label


def _verify_key_identity(root: Path, key: bytes, version: str) -> None:
    identity = root / "collection-state" / "key-identities" / f"{version}.sha256"
    fingerprint = hashlib.sha256(key).hexdigest()
    identity.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(identity, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if identity.read_text(encoding="ascii").strip() != fingerprint:
            raise CollectionError(
                "HMAC key does not match its existing OBSERVATORY_HMAC_KEY_VERSION"
            ) from None
        return
    with os.fdopen(fd, "w", encoding="ascii") as output:
        output.write(fingerprint + "\n")
        output.flush()
        os.fsync(output.fileno())


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    _write_bytes_atomic(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def normalize_jobtech_hit(
    hit: dict[str, Any],
    observed_at: str,
    *,
    scope_id: str | None = None,
    sweep_id: str | None = None,
    references: ReferenceTables | None = None,
) -> dict[str, Any]:
    source_id = hit.get("id")
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("JobTech hit has no non-empty id")

    address = hit.get("workplace_address")
    if not isinstance(address, dict):
        address = {}

    raw_country = hit.get("country_code") or address.get("country_code")
    if raw_country not in (JOBTECH_EXPECTED_COUNTRY, JOBTECH_SWEDEN_COUNTRY_CODE):
        raise ValueError("JobTech hit must have country_code SE or 199")
    country = JOBTECH_EXPECTED_COUNTRY

    enrichment = enrich_hit(hit, references)
    region = enrichment["region"]
    occupation = enrichment["occupation"]
    skills = enrichment["skills"]
    requirements = enrichment["requirements"]
    record: dict[str, Any] = {
        "source": "jobtech",
        "source_id": source_id,
        "observed_at": _iso(observed_at),
        "first_published": hit.get("publication_date"),
        "last_modified": hit.get("last_publication_date"),
        "removed_at": hit.get("removed_date"),
        "nuts_code": region["nuts_code"],
        "nuts_label": region["nuts_label"],
        "region_mapping_status": region["status"],
        "region_mapping_method": region["method"],
        "nuts_version": region["nuts_version"],
        "country": country,
        "esco_occupation_uri": occupation["uri"],
        "esco_occupation_label": occupation["label"],
        "occupation_mapping_status": occupation["status"],
        "occupation_mapping_confidence": occupation["confidence"],
        "occupation_mapping_method": occupation["method"],
        "source_language": occupation["source_language"],
        "jobtech_taxonomy_version": occupation["jobtech_taxonomy_version"],
        "esco_version": occupation["esco_version"],
        "lang": "sv",
        "skill_uris": sorted(skill["uri"] for skill in skills if skill["uri"]),
        "skill_mappings": skills,
        # The contract a posting offers, from three closed-vocabulary source fields. Written as
        # nine flat keys rather than a nested block because stg_postings' `columns` map is the
        # schema gate downstream, and a flat key is the shape it can type-check.
        "employment_type_code": requirements["employment_type"]["code"],
        "employment_type_label": requirements["employment_type"]["label"],
        "employment_type_mapping_status": requirements["employment_type"]["status"],
        "working_hours_type_code": requirements["working_hours_type"]["code"],
        "working_hours_type_label": requirements["working_hours_type"]["label"],
        "working_hours_type_mapping_status": requirements["working_hours_type"]["status"],
        "duration_code": requirements["duration"]["code"],
        "duration_label": requirements["duration"]["label"],
        "duration_mapping_status": requirements["duration"]["status"],
        "number_of_vacancies": hit.get("number_of_vacancies"),
    }
    if scope_id is not None:
        record["scope_id"] = scope_id
    if sweep_id is not None:
        record["sweep_id"] = sweep_id
    return record


def collect_jobtech(
    source: Path,
    target: Path,
    observed_at: str,
    key: bytes,
    *,
    scope_id: str | None = None,
    sweep_id: str | None = None,
) -> int:
    """Normalize and sanitize all hits in one recorded response atomically."""
    if source.resolve() == target.resolve():
        raise ValueError("input and output paths must differ")
    payload = json.loads(source.read_text(encoding="utf-8"))
    hits = payload.get("hits") if isinstance(payload, dict) else None
    if not isinstance(hits, list):
        raise ValueError("JobTech response must contain a hits list")

    references = load_references()
    rows: list[bytes] = []
    for hit in hits:
        if not isinstance(hit, dict):
            raise ValueError("each JobTech hit must be an object")
        safe = sanitize_record(
            normalize_jobtech_hit(
                hit,
                observed_at,
                scope_id=scope_id,
                sweep_id=sweep_id,
                references=references,
            ),
            key,
        )
        rows.append((json.dumps(safe, ensure_ascii=False) + "\n").encode())
    _write_bytes_atomic(target, b"".join(rows))
    return len(rows)


def _http_transport(url: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError:
        raise
    except (URLError, TimeoutError, OSError) as error:
        raise TransientTransportError(f"transport failure: {error}") from error
    if not isinstance(payload, dict):
        raise CollectionError("JobTech response must be a JSON object")
    return payload


def _status_code(error: BaseException) -> int | None:
    return error.code if isinstance(error, HTTPError) else None


def _retry_after(error: BaseException, now: datetime) -> float | None:
    if not isinstance(error, HTTPError):
        return None
    raw = error.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            return max(0.0, (parsedate_to_datetime(raw).astimezone(UTC) - now).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _is_retryable(error: BaseException) -> bool:
    code = _status_code(error)
    if code is not None:
        return code in {408, 429, 500, 502, 503, 504}
    return isinstance(
        error, (URLError, TimeoutError, ConnectionError, OSError, TransientTransportError)
    )


def _request_page(
    url: str,
    policy: RetryPolicy,
    *,
    transport: PageTransport,
    sleeper: Callable[[float], None],
    now: Callable[[], datetime],
    monotonic_now: Callable[[], float],
    random_value: Callable[[], float],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    started = monotonic_now()
    last_error: BaseException | None = None
    for attempt in range(1, policy.max_attempts + 1):
        elapsed = monotonic_now() - started
        remaining = policy.deadline_s - elapsed
        if remaining <= 0:
            break
        events.append({"event": "request", "attempt": attempt, "url": url})
        try:
            result = transport(url, min(policy.timeout_s, remaining))
            if monotonic_now() - started > policy.deadline_s:
                raise CollectionError("request exceeded retry deadline")
            events.append({"event": "response", "attempt": attempt, "status": 200})
            return result
        except BaseException as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            last_error = error
            code = _status_code(error)
            events.append(
                {
                    "event": "response",
                    "attempt": attempt,
                    "status": code,
                    "error": type(error).__name__,
                }
            )
            if not _is_retryable(error) or attempt == policy.max_attempts:
                raise CollectionError(
                    f"request failed after {attempt} attempt(s): {error}"
                ) from error
            delay = _retry_after(error, now())
            if delay is None:
                delay = min(policy.max_backoff_s, policy.backoff_s * (2 ** (attempt - 1)))
                delay += random_value() * policy.jitter_s
            remaining = policy.deadline_s - (monotonic_now() - started)
            if remaining <= 0:
                break
            delay = min(delay, remaining)
            events.append({"event": "retry", "attempt": attempt, "delay_s": delay, "status": code})
            sleeper(delay)
    raise CollectionError(f"request retry deadline exceeded: {last_error}") from last_error


def _page_total(payload: Mapping[str, Any]) -> int:
    total = payload.get("total")
    if isinstance(total, dict):
        total = total.get("value")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise CollectionError("JobTech response must contain a non-negative integer total.value")
    return total


def _hits(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    hits = payload.get("hits")
    if not isinstance(hits, list):
        raise CollectionError("JobTech response must contain a hits list")
    if not all(isinstance(hit, dict) for hit in hits):
        raise CollectionError("each JobTech hit must be an object")
    return cast(list[dict[str, Any]], hits)


def _verify_scope_filter(hits: list[dict[str, Any]], occupation_field: str | None) -> None:
    """Prove the requested filter was applied, because the API drops unknown params silently.

    A camelCase `occupationField` returned all 40,649 Swedish ads with no error, so a typo in a
    filter name would collect everything under a scope claiming to be narrow. `q` has no
    wire-visible counterpart in a sanitized record; the country filter is verified hit by hit in
    `normalize_jobtech_hit`. A page too short to carry a meaningful ratio proves nothing either
    way, and an ignored parameter is guaranteed to show up on the full pages before it.
    """
    if occupation_field is None or len(hits) < JOBTECH_FILTER_MIN_SAMPLE:
        return
    matching = sum(
        1
        for hit in hits
        if isinstance(field := hit.get("occupation_field"), dict)
        and field.get("concept_id") == occupation_field
    )
    if matching <= len(hits) * JOBTECH_FILTER_MAJORITY_SHARE:
        raise CollectionError(
            f"JobTech did not apply the occupation-field filter: only {matching} of {len(hits)} "
            f"hits report {occupation_field}"
        )


def _verify_reachable(total: int | None, page_size: int) -> None:
    """Refuse a scope whose last row cannot be reached, because unseen rows read as removed.

    Collecting the reachable prefix and calling it a complete sweep is the worst available
    outcome: every posting past the cap would be closed as an inferred absence on the next sweep,
    inventing removals that never happened and a duration for each. A scope larger than the
    window has to be split into slices that are each individually complete.

    Offsets only ever land on multiples of page_size, so the last usable offset is the largest
    such multiple within the cap. Rounding up instead would let a non-divisor page size (30, say)
    pass the check and then die at offset 2010 with 67 pages already checkpointed.
    """
    reachable = JOBTECH_MAX_OFFSET // page_size * page_size + page_size
    if total is None or total <= reachable:
        return
    raise CollectionError(
        f"scope reports {total} records but only {reachable} are reachable "
        f"(offset cap {JOBTECH_MAX_OFFSET}, page size {page_size}); split the scope into slices "
        f"that each fit, and never publish a truncated sweep as complete"
    )


def _acquire_lock(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise CollectionError(f"collection is already locked: {path}") from error


def _manifest_matches(manifest: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    fields = (
        "source",
        "scope_id",
        "scope_hash",
        "scope_json",
        "sweep_id",
        "observed_at",
        "page_size",
        "hmac_key_version",
        "source_version",
        "licence_reference",
        "access_method",
        "approval_status",
        "expected_country",
        "freshness_threshold_hours",
        "coverage_limitations",
        "reference_hashes",
        "nuts_version",
        "jobtech_taxonomy_version",
        "esco_version",
    )
    for field in fields:
        if manifest.get(field) != expected.get(field):
            raise CollectionError(f"resume metadata mismatch for {field}")


def _page_file(state_dir: Path, index: int, suffix: str) -> Path:
    return state_dir / "pages" / f"page-{index:06d}.{suffix}"


def _page_ndjson(
    hits: list[dict[str, Any]],
    observed_at: str,
    scope_id: str,
    sweep_id: str,
    key: bytes,
    references: ReferenceTables,
) -> tuple[bytes, list[str]]:
    rows: list[bytes] = []
    ids: list[str] = []
    for hit in hits:
        native_id = hit.get("id")
        if not isinstance(native_id, str) or not native_id:
            raise CollectionError("JobTech hit has no non-empty id")
        ids.append(native_id)
        safe = sanitize_record(
            normalize_jobtech_hit(
                hit, observed_at, scope_id=scope_id, sweep_id=sweep_id, references=references
            ),
            key,
        )
        rows.append((json.dumps(safe, ensure_ascii=False) + "\n").encode())
    return b"".join(rows), ids


def collect_jobtech_sweep(
    root: Path,
    key: bytes,
    *,
    query: str | None = None,
    observed_at: str | None = None,
    page_size: int | None = None,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    transport: PageTransport | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic_now: Callable[[], float] = monotonic,
    random_value: Callable[[], float] = random.random,
    resume: bool = False,
    sweep_id: str | None = None,
    occupation_field: str | None = None,
) -> dict[str, Any]:
    """Run or resume one serial, scope-complete JobTech search sweep."""
    if len(key) < 32:
        raise ValueError("HMAC key must be at least 32 bytes")
    state_manifest: dict[str, Any] | None = None
    if resume and sweep_id is not None:
        checkpoint = root / "collection-state" / sweep_id / "manifest.json"
        if checkpoint.exists():
            state_manifest = cast(
                dict[str, Any], json.loads(checkpoint.read_text(encoding="utf-8"))
            )
            saved_scope = cast(dict[str, Any], json.loads(str(state_manifest["scope_json"])))
            saved_params = cast(dict[str, Any], saved_scope["params"])
            # Rehydrate whichever selector the saved scope carries: guessing "q" would resume an
            # occupation-field sweep as a keyword sweep, under a scope_id that no longer matches.
            if query is None and occupation_field is None:
                query = str(saved_params["q"]) if "q" in saved_params else None
                occupation_field = (
                    str(saved_params["occupation-field"])
                    if "occupation-field" in saved_params
                    else None
                )
            page_size = page_size if page_size is not None else int(saved_params["limit"])
            observed_at = observed_at or str(state_manifest["observed_at"])
    query, occupation_field = _selector(query, occupation_field)
    page_size = page_size if page_size is not None else DEFAULT_PAGE_SIZE
    selected = query if query is not None else occupation_field
    if selected is None or not selected.strip():
        raise ValueError("query or occupation field must not be empty")
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between 1 and 100")
    if policy.max_attempts < 1 or policy.deadline_s <= 0 or policy.timeout_s <= 0:
        raise ValueError("retry attempts, deadline, and timeout must be positive")
    key_version = _key_version(key)
    references = load_references()
    _verify_key_identity(root, key, key_version)
    observed = _iso(observed_at or clock())
    scope_id, scope_hash, scope_json = _scope(query, page_size, occupation_field)
    effective_sweep_id = sweep_id or f"{_filename_timestamp(observed)}-{scope_hash[:12]}"
    if not effective_sweep_id.replace("-", "").isalnum():
        raise ValueError("sweep_id contains unsafe filename characters")

    raw_root = root / "collections"
    state_dir = root / "collection-state" / effective_sweep_id
    final_dir = raw_root / "jobtech" / scope_id / effective_sweep_id
    final_manifest = final_dir / "manifest.json"
    expected = {
        "source": "jobtech",
        "scope_id": scope_id,
        "scope_hash": scope_hash,
        "scope_json": scope_json,
        "sweep_id": effective_sweep_id,
        "observed_at": observed,
        "page_size": page_size,
        "hmac_key_version": key_version,
        "source_version": JOBTECH_SOURCE_VERSION,
        "licence_reference": JOBTECH_LICENCE_REFERENCE,
        "access_method": JOBTECH_ACCESS_METHOD,
        "approval_status": JOBTECH_APPROVAL_STATUS,
        "expected_country": JOBTECH_EXPECTED_COUNTRY,
        "freshness_threshold_hours": JOBTECH_FRESHNESS_THRESHOLD_HOURS,
        "coverage_limitations": _coverage_limitations(occupation_field),
        **reference_provenance(references),
    }
    if final_manifest.exists():
        existing = cast(dict[str, Any], json.loads(final_manifest.read_text(encoding="utf-8")))
        _manifest_matches(existing, expected)
        if existing.get("status") != "complete" and not resume:
            raise CollectionError("partition exists but is not complete; use --resume")
        observations = final_dir / "observations.ndjson"
        if not observations.exists():
            raise CollectionError("completed partition is missing observations.ndjson")
        content_hash = hashlib.sha256(observations.read_bytes()).hexdigest()
        if existing.get("observations_hash") != content_hash:
            raise CollectionError("completed partition observation hash mismatch")
        if existing.get("status") != "complete":
            complete = {**existing, "status": "complete", "completed_at": _iso(clock())}
            _write_json_atomic(final_manifest, complete)
            return complete
        return existing
    if state_dir.exists() and not resume:
        raise CollectionError(f"in-progress collection exists; use --resume: {state_dir}")

    lock_path = state_dir.with_suffix(".lock")
    lock_fd = _acquire_lock(lock_path)
    events: list[dict[str, Any]] = []
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = state_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            _manifest_matches(manifest, expected)
            pages = manifest.get("pages", [])
            if not isinstance(pages, list):
                raise CollectionError("checkpoint pages must be a list")
            if manifest.get("completed_pages") != len(pages):
                raise CollectionError(
                    "checkpoint completed page count does not match its inventory"
                )
        else:
            manifest = {
                **expected,
                "schema_version": SCHEMA_VERSION,
                "collector_version": COLLECTOR_VERSION,
                "partition_id": f"jobtech/{scope_id}/{effective_sweep_id}",
                "run_id": f"run-{effective_sweep_id}",
                "started_at": _iso(clock()),
                "completed_at": None,
                "status": "in_progress",
                "failure_code": None,
                "failure_message": None,
                "expected_pages": None,
                "completed_pages": 0,
                "expected_rows": None,
                "row_count": 0,
                "response_hashes_json": "[]",
                "pages": [],
                "events": [],
            }
            pages = []
            _write_json_atomic(manifest_path, manifest)

        total: int | None = manifest.get("expected_rows")
        page_index = len(pages)
        seen_ids: set[str] = set()
        all_rows: list[bytes] = []
        for completed_index in range(page_index):
            page_meta = pages[completed_index]
            if not isinstance(page_meta, dict):
                raise CollectionError(f"checkpoint page {completed_index} is not an object")
            raw_path = _page_file(state_dir, completed_index, "json")
            safe_path = _page_file(state_dir, completed_index, "ndjson")
            if not raw_path.exists() or not safe_path.exists():
                raise CollectionError(f"checkpoint page {completed_index} is missing")
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
            page_total = _page_total(payload)
            page_hits = _hits(payload)
            _verify_scope_filter(page_hits, occupation_field)
            if total is None:
                total = page_total
            if page_total != total:
                raise CollectionError("JobTech total changed in checkpoint")
            offset = completed_index * page_size
            if page_meta.get("index") != completed_index or page_meta.get("offset") != offset:
                raise CollectionError(f"checkpoint page {completed_index} has an invalid inventory")
            native_ids: list[str] = []
            for hit in page_hits:
                native_id = hit.get("id")
                if not isinstance(native_id, str) or not native_id:
                    raise CollectionError("checkpoint contains a hit without an id")
                native_ids.append(native_id)
            if len(set(native_ids)) != len(native_ids) or seen_ids.intersection(native_ids):
                raise CollectionError("duplicate JobTech id across pages")
            if page_meta.get("row_count") != len(native_ids):
                raise CollectionError(f"checkpoint page {completed_index} has an invalid row count")
            if (
                page_meta.get("ids_hash")
                != hashlib.sha256("\n".join(native_ids).encode()).hexdigest()
            ):
                raise CollectionError(f"checkpoint page {completed_index} has an invalid id hash")
            if len(native_ids) > page_size or (
                total > offset + len(native_ids) and len(native_ids) != page_size
            ):
                raise CollectionError(
                    f"checkpoint page {completed_index} has an invalid page length"
                )
            seen_ids.update(native_ids)
            if hashlib.sha256(raw_path.read_bytes()).hexdigest() != page_meta.get("raw_hash"):
                raise CollectionError(f"checkpoint hash mismatch for page {completed_index}")
            safe_bytes = safe_path.read_bytes()
            if hashlib.sha256(safe_bytes).hexdigest() != page_meta.get("safe_hash"):
                raise CollectionError(f"checkpoint safe hash mismatch for page {completed_index}")
            if len(safe_bytes.splitlines()) != len(native_ids):
                raise CollectionError(
                    f"checkpoint page {completed_index} has an invalid safe row count"
                )
            all_rows.extend(safe_bytes.splitlines(keepends=True))

        _verify_reachable(total, page_size)
        while total is None or page_index * page_size < total:
            offset = page_index * page_size
            query_params = {**_search_params(query, page_size, occupation_field), "offset": offset}
            url = f"{JOBTECH_SEARCH}?{urlencode(query_params)}"
            payload = _request_page(
                url,
                policy,
                transport=transport or _http_transport,
                sleeper=sleeper,
                now=clock,
                monotonic_now=monotonic_now,
                random_value=random_value,
                events=events,
            )
            page_total = _page_total(payload)
            hits = _hits(payload)
            _verify_scope_filter(hits, occupation_field)
            if total is None:
                total = page_total
                _verify_reachable(total, page_size)
            if page_total != total:
                raise CollectionError("JobTech total changed during sweep")
            if len(hits) > page_size or (total > offset + len(hits) and len(hits) != page_size):
                raise CollectionError(
                    "JobTech page is short or larger than the requested page size"
                )
            if offset >= total and hits:
                raise CollectionError("JobTech returned an unexpected extra page")
            raw_bytes = (json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n").encode()
            safe_bytes, native_ids = _page_ndjson(
                hits, observed, scope_id, effective_sweep_id, key, references
            )
            if len(set(native_ids)) != len(native_ids) or seen_ids.intersection(native_ids):
                raise CollectionError("duplicate JobTech id across pages")
            seen_ids.update(native_ids)
            raw_path = _page_file(state_dir, page_index, "json")
            safe_path = _page_file(state_dir, page_index, "ndjson")
            _write_bytes_atomic(raw_path, raw_bytes)
            _write_bytes_atomic(safe_path, safe_bytes)
            pages.append(
                {
                    "index": page_index,
                    "offset": offset,
                    "row_count": len(hits),
                    "raw_hash": hashlib.sha256(raw_bytes).hexdigest(),
                    "safe_hash": hashlib.sha256(safe_bytes).hexdigest(),
                    "ids_hash": hashlib.sha256("\n".join(native_ids).encode()).hexdigest(),
                }
            )
            all_rows.extend(safe_bytes.splitlines(keepends=True))
            page_index += 1
            manifest.update(
                {
                    "expected_pages": (total + page_size - 1) // page_size if total else 1,
                    "completed_pages": page_index,
                    "expected_rows": total,
                    "row_count": len(all_rows),
                    "pages": pages,
                    "events": events,
                }
            )
            _write_json_atomic(manifest_path, manifest)
            if total is not None and page_index * page_size < total:
                sleeper(policy.pause_s)

        if total is None:
            total = 0
        expected_pages = (total + page_size - 1) // page_size if total else 1
        if len(pages) != expected_pages or len(all_rows) != total:
            raise CollectionError("sweep totals do not reconcile")
        if len(seen_ids) != len(all_rows):
            raise CollectionError("sanitized observation IDs are not unique")

        temporary_dir = final_dir.with_name(f".{final_dir.name}.publishing")
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)
        temporary_dir.mkdir(parents=True)
        observations_bytes = b"".join(all_rows)
        _write_bytes_atomic(temporary_dir / "observations.ndjson", observations_bytes)
        _sync_directory(temporary_dir)
        complete = {
            **manifest,
            "status": "complete",
            "completed_at": _iso(clock()),
            "expected_pages": expected_pages,
            "completed_pages": len(pages),
            "expected_rows": total,
            "row_count": len(all_rows),
            "observations_hash": hashlib.sha256(observations_bytes).hexdigest(),
            "response_hashes_json": json.dumps([page["raw_hash"] for page in pages]),
            "events": events,
        }
        _write_json_atomic(temporary_dir / "manifest.json", {**complete, "status": "in_progress"})
        if final_dir.exists():
            raise CollectionError(f"completed partition path already exists: {final_dir}")
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary_dir, final_dir)
        _sync_directory(final_dir.parent)
        _write_json_atomic(final_manifest, complete)
        _write_json_atomic(manifest_path, complete)
        return complete
    except BaseException as error:
        if not isinstance(error, (KeyboardInterrupt, SystemExit)):
            try:
                if state_dir.exists():
                    checkpoint = state_dir / "manifest.json"
                    current = (
                        json.loads(checkpoint.read_text(encoding="utf-8"))
                        if checkpoint.exists()
                        else {}
                    )
                    current.update(
                        {
                            **expected,
                            "status": "failed",
                            "failure_code": type(error).__name__,
                            "failure_message": str(error),
                            "events": events,
                        }
                    )
                    _write_json_atomic(state_dir / "manifest.json", current)
            except OSError:
                pass
        raise
    finally:
        os.close(lock_fd)
        with suppress(FileNotFoundError):
            lock_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect recorded or live JobTech observations")
    subparsers = parser.add_subparsers(dest="command")

    recorded = subparsers.add_parser("recorded", help="normalize one recorded response offline")
    recorded.add_argument("source", type=Path)
    recorded.add_argument("target", type=Path)
    recorded.add_argument("--observed-at", default=None)

    sweep = subparsers.add_parser("sweep", help="collect one complete live JobTech search sweep")
    sweep.add_argument("--root", type=Path, default=ROOT / "data" / "raw")
    # Exactly one selector defines the scope, so argparse refuses the combination outright.
    scope_selector = sweep.add_mutually_exclusive_group()
    scope_selector.add_argument("--query", default=None)
    scope_selector.add_argument(
        "--occupation-field",
        default=None,
        help=f"JobTech occupation field concept id, e.g. Data/IT is {JOBTECH_DATA_IT_FIELD}",
    )
    sweep.add_argument("--observed-at", default=None)
    sweep.add_argument("--sweep-id", default=None)
    sweep.add_argument("--page-size", type=int, default=None)
    sweep.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    sweep.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    sweep.add_argument("--retry-deadline", type=float, default=DEFAULT_RETRY_DEADLINE_S)
    sweep.add_argument("--pause", type=float, default=DEFAULT_PAUSE_S)
    sweep.add_argument("--resume", action="store_true")

    argv = sys.argv[1:]
    if argv and argv[0] not in {"recorded", "sweep", "-h", "--help"}:
        argv.insert(0, "recorded")
    args = parser.parse_args(argv)
    if args.command == "recorded":
        key = key_from_env()
        observed_at = args.observed_at or _iso(datetime.now(UTC))
        count = collect_jobtech(args.source, args.target, observed_at, key)
        print(f"wrote {args.target} ({count} observations; not a complete sweep)")
        return 0
    if args.command == "sweep":
        key = key_from_env()
        policy = RetryPolicy(
            timeout_s=args.timeout,
            max_attempts=args.max_attempts,
            deadline_s=args.retry_deadline,
            pause_s=args.pause,
        )
        manifest = collect_jobtech_sweep(
            args.root,
            key,
            query=args.query,
            observed_at=args.observed_at,
            page_size=args.page_size,
            policy=policy,
            resume=args.resume,
            sweep_id=args.sweep_id,
            occupation_field=args.occupation_field,
        )
        print(
            f"sweep {manifest['status']}: {manifest['partition_id']} "
            f"({manifest['row_count']} rows, {manifest['completed_pages']} pages)"
        )
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
