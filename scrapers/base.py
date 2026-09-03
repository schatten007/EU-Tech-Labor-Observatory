"""Collector Interface (SCRAPER_ROADMAP.md Increment 1).

The abstract contract every source collector implements. ``NormalizedRecord``
is the SAFE_FIELDS allowlist from SCRAPERS.md § Output contract, and its field
set mirrors ``transform/models/staging/stg_postings.sql`` so the main checkout
can consume collector output without changes. Sweden's live JobTech collector
was the blueprint.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Literal, Self

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

logger = structlog.get_logger()

# All HTTP calls use a 30 s timeout (charter Rule 3 in the lab instructions).
REQUEST_TIMEOUT_SECONDS = 30.0

#: Mapping-status vocabulary shared by the region and occupation dimensions.
MappingStatus = Literal["mapped", "ambiguous", "low_confidence", "unmapped", "not_present"]

#: The SAFE_FIELDS allowlist (SCRAPERS.md § Output contract).
#: Never add title, description, employer, contacts, URLs, native identifiers,
#: street addresses, postcodes, or any free text.
SAFE_FIELDS: frozenset[str] = frozenset(
    {
        "source",
        "source_id",
        "scope_id",
        "sweep_id",
        "observed_at",
        "first_published",
        "last_modified",
        "removed_at",
        "nuts_code",
        "nuts_label",
        "region_mapping_status",
        "region_mapping_method",
        "nuts_version",
        "country",
        "esco_occupation_uri",
        "esco_occupation_label",
        "occupation_mapping_status",
        "occupation_mapping_confidence",
        "occupation_mapping_method",
        "source_language",
        "jobtech_taxonomy_version",
        "esco_version",
        "skill_mappings",
        "lang",
        "number_of_vacancies",
    }
)


class RawRecord(BaseModel):
    """One source-native posting before normalization.

    Extra source-native fields are tolerated here so a collector can hand the
    full raw payload to :meth:`BaseCollector.parse`. ``native_id`` never leaves
    this class: :meth:`BaseCollector.normalize` pseudonymizes it into
    ``NormalizedRecord.source_id``.
    """

    model_config = ConfigDict(extra="allow")

    native_id: str = Field(min_length=1)
    payload: dict[str, Any]


class NormalizedRecord(BaseModel):
    """One posting on the SAFE_FIELDS allowlist, ready for the NDJSON writer.

    ``extra="forbid"`` is the enforcement point of the no-personal-data rule:
    any unknown field (title, description, employer, contact, URL, ...) is
    rejected outright instead of being written to disk.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    source_id: str = Field(min_length=64, max_length=64)  # HMAC-SHA256 hex digest
    scope_id: str
    sweep_id: str
    observed_at: datetime
    first_published: datetime | None = None
    last_modified: datetime | None = None
    removed_at: datetime | None = None
    nuts_code: str | None = None
    nuts_label: str | None = None
    region_mapping_status: MappingStatus = "unmapped"
    region_mapping_method: str = "not_implemented"
    nuts_version: str = "NUTS-2024"
    country: str  # ISO 3166-1 alpha-2
    esco_occupation_uri: str | None = None
    esco_occupation_label: str | None = None
    occupation_mapping_status: MappingStatus = "unmapped"
    occupation_mapping_confidence: str | None = None
    occupation_mapping_method: str = "not_implemented"
    source_language: str
    jobtech_taxonomy_version: str = ""  # v30 for JobTech sources, empty otherwise
    esco_version: str = "1.2.1"
    skill_mappings: list[dict[str, str]] = Field(default_factory=list)
    lang: str
    number_of_vacancies: int = Field(default=1, ge=0)

    def model_dump_ndjson(self) -> dict[str, Any]:
        """Serialization form for one line of ``observations.ndjson``."""
        return self.model_dump(mode="json")


class BaseCollector(ABC):
    """Abstract collector contract: fetch -> parse -> normalize -> write.

    Concrete collectors implement :meth:`fetch`, :meth:`parse`, and
    :meth:`normalize`; :meth:`collect` drives the pipeline. All HTTP goes
    through the injected :class:`httpx.AsyncClient` with a 30 s timeout.
    """

    source: ClassVar[str] = ""
    country: ClassVar[str] = ""

    def __init__(
        self,
        *,
        scope_id: str,
        sweep_id: str,
        observed_at: datetime,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.scope_id = scope_id
        self.sweep_id = sweep_id
        self.observed_at = observed_at
        self._client = httpx.AsyncClient(timeout=timeout)
        self._log = logger.bind(source=self.source, scope_id=self.scope_id, sweep_id=self.sweep_id)
        #: Sweep progress counters, populated by each concrete collector's fetch().
        self.total_elements = 0
        self.total_pages = 0
        self.completed_pages = 0

    @abstractmethod
    def fetch(self) -> AsyncIterator[RawRecord]:
        """Return an async iterator yielding one :class:`RawRecord` per posting.

        Implementations declare this as an ``async def`` generator and must
        check robots.txt before the first request, pace at one request per
        second or more per host, and retry transient failures (429/5xx) with
        exponential backoff honoring ``Retry-After``.
        """

    @abstractmethod
    def parse(self, raw: RawRecord) -> dict[str, Any]:
        """Extract the source-native fields the allowlist needs from a raw record."""

    @abstractmethod
    def normalize(self, parsed: dict[str, Any]) -> NormalizedRecord:
        """Map parsed fields onto the SAFE_FIELDS allowlist.

        The source-native identifier must be HMAC-SHA256 pseudonymized into
        ``NormalizedRecord.source_id`` with the shared ``OBSERVATORY_HMAC_KEY``
        before the record is returned.
        """

    async def collect(self) -> AsyncIterator[NormalizedRecord]:
        """Run the full pipeline for one sweep."""
        count = 0
        async for raw in self.fetch():
            record = self.normalize(self.parse(raw))
            count += 1
            yield record
        self._log.info("collector_pipeline_done", rows=count)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Release the underlying HTTP client."""
        await self._client.aclose()


def utc_iso(value: datetime) -> str:
    """Format a datetime as the charter's ``YYYY-MM-DDTHH:MM:SSZ`` stamp."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class SweepWriter:
    """Writes one collection partition: ``observations.ndjson`` + ``manifest.json``.

    The manifest reconciles ``status == "complete"`` with
    ``expected_pages == completed_pages`` and ``expected_rows == row_count``,
    per SCRAPERS.md § Output contract.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def write_partition(
        self,
        *,
        source: str,
        scope_id: str,
        scope_params: Mapping[str, object],
        sweep_id: str,
        run_id: str,
        observed_at: datetime,
        started_at: datetime,
        rows: Sequence[NormalizedRecord],
        expected_pages: int,
        completed_pages: int,
        expected_rows: int,
        hmac_key_version: str,
        source_version: str,
        licence_reference: str,
        access_method: str,
        expected_country: str,
        freshness_threshold_hours: int,
        coverage_limitations: str,
        reference_hashes: str = "",
        completed_at: datetime | None = None,
    ) -> Path:
        """Write the partition and return its directory."""
        partition = self.root / "raw" / "collections" / source / scope_id / sweep_id
        partition.mkdir(parents=True, exist_ok=True)

        row_count = len(rows)
        expected_pages_ok = expected_pages == completed_pages
        expected_rows_ok = expected_rows == row_count
        status = "complete" if expected_pages_ok and expected_rows_ok else "partial"

        scope_json = json.dumps(scope_params, sort_keys=True, ensure_ascii=False)
        scope_hash = hashlib.sha256(scope_json.encode("utf-8")).hexdigest()

        manifest: dict[str, object] = {
            "source": source,
            "scope_id": scope_id,
            "scope_hash": scope_hash,
            "scope_json": scope_json,
            "partition_id": f"{scope_id}/{sweep_id}",
            "sweep_id": sweep_id,
            "run_id": run_id,
            "observed_at": utc_iso(observed_at),
            "started_at": utc_iso(started_at),
            "completed_at": utc_iso(completed_at or datetime.now(UTC)),
            "status": status,
            "expected_pages": expected_pages,
            "completed_pages": completed_pages,
            "expected_rows": expected_rows,
            "row_count": row_count,
            "hmac_key_version": hmac_key_version,
            "source_version": source_version,
            "licence_reference": licence_reference,
            "access_method": access_method,
            "approval_status": "approved",
            "expected_country": expected_country,
            "freshness_threshold_hours": freshness_threshold_hours,
            "coverage_limitations": coverage_limitations,
            "reference_hashes": reference_hashes,
            "nuts_version": "NUTS-2024",
            "jobtech_taxonomy_version": "",
            "esco_version": "1.2.1",
        }

        (partition / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        with (partition / "observations.ndjson").open("w", encoding="utf-8") as handle:
            for record in rows:
                handle.write(json.dumps(record.model_dump_ndjson(), ensure_ascii=False) + "\n")

        self._log_write(partition, row_count, status)
        return partition

    def _log_write(self, partition: Path, row_count: int, status: str) -> None:
        logger.info(
            "sweep_partition_written", partition=str(partition), row_count=row_count, status=status
        )
