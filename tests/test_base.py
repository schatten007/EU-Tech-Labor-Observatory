"""Unit tests for the Collector Interface skeleton (Task 2 of the CBOP increment)."""

import asyncio
import inspect
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from scrapers.base import SAFE_FIELDS, BaseCollector, NormalizedRecord, RawRecord


def base_kwargs(**overrides: object) -> dict[str, Any]:
    """A valid SAFE_FIELDS record; tests override one field at a time."""
    kwargs: dict[str, Any] = {
        "source": "cbop",
        "source_id": "a" * 64,
        "scope_id": "pl-all-active",
        "sweep_id": "20260821T000000Z",
        "observed_at": datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        "country": "PL",
        "source_language": "pl",
        "lang": "pl",
        "number_of_vacancies": 1,
    }
    kwargs.update(overrides)
    return kwargs


def test_safe_fields_match_the_charter_allowlist() -> None:
    assert "source_id" in SAFE_FIELDS
    assert "number_of_vacancies" in SAFE_FIELDS
    assert "title" not in SAFE_FIELDS
    assert "description" not in SAFE_FIELDS
    assert "salary" not in SAFE_FIELDS


def test_normalized_record_forbids_pii_and_free_text() -> None:
    with pytest.raises(ValidationError):
        NormalizedRecord(**base_kwargs(title="Private title"))


def test_normalized_record_accepts_the_charter_shape() -> None:
    record = NormalizedRecord(**base_kwargs())
    assert record.country == "PL"
    assert record.nuts_version == "NUTS-2024"
    assert record.esco_version == "1.2.1"
    assert record.region_mapping_status == "unmapped"
    assert record.model_dump_ndjson()["observed_at"] == "2026-08-21T12:00:00Z"


def test_base_collector_is_abstract() -> None:
    assert inspect.isabstract(BaseCollector)
    assert {"fetch", "parse", "normalize"} <= set(BaseCollector.__abstractmethods__)


class _StubCollector(BaseCollector):
    source: ClassVar[str] = "cbop"
    country: ClassVar[str] = "PL"

    async def fetch(self) -> AsyncIterator[RawRecord]:
        yield RawRecord(native_id="native-1", payload={})

    def parse(self, raw: RawRecord) -> dict[str, Any]:
        return {"native_id": raw.native_id}

    def normalize(self, parsed: dict[str, Any]) -> NormalizedRecord:
        return NormalizedRecord(**base_kwargs())


def test_collect_pipeline_yields_normalized_records() -> None:
    async def run() -> list[NormalizedRecord]:
        async with _StubCollector(
            scope_id="pl-all-active",
            sweep_id="sweep-1",
            observed_at=datetime(2026, 8, 21, tzinfo=UTC),
        ) as collector:
            return [record async for record in collector.collect()]

    records = asyncio.run(run())
    assert len(records) == 1
    assert records[0].source == "cbop"
    assert records[0].country == "PL"
