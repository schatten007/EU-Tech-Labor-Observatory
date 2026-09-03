"""Unit tests for the SchemaValidator (Task 5)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from scrapers.base import NormalizedRecord
from scrapers.validate import SchemaValidator


def base_kwargs(**overrides: Any) -> dict[str, Any]:
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


def test_validate_accepts_allowlist_record() -> None:
    validator = SchemaValidator()
    record = NormalizedRecord(**base_kwargs())
    assert validator.validate(record) is record


def test_validate_rejects_unknown_fields_via_allowlist() -> None:
    validator = SchemaValidator(allowlist=frozenset({"source"}))
    with pytest.raises(ValueError, match="outside SAFE_FIELDS"):
        validator.validate(NormalizedRecord(**base_kwargs()))


def test_arrow_schema_covers_the_allowlist() -> None:
    schema = SchemaValidator().arrow_schema()
    names = set(schema.names)
    assert "source_id" in names
    assert "number_of_vacancies" in names
    assert "skill_mappings" in names
    assert "title" not in names


def test_write_ndjson_writes_one_line_per_record(tmp_path: Path) -> None:
    validator = SchemaValidator()
    path = tmp_path / "observations.ndjson"
    records = [
        NormalizedRecord(**base_kwargs()),
        NormalizedRecord(**base_kwargs(source_id="b" * 64)),
    ]

    count = validator.write_ndjson(records, path)

    assert count == 2
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["country"] == "PL"
    assert "title" not in first


def test_write_parquet_roundtrips(tmp_path: Path) -> None:
    validator = SchemaValidator()
    path = tmp_path / "observations.parquet"

    count = validator.write_parquet([NormalizedRecord(**base_kwargs())], path)

    assert count == 1
    table = pq.read_table(path)
    assert table.num_rows == 1
    assert "source_id" in table.column_names
    assert "number_of_vacancies" in table.column_names
