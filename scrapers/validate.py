"""SchemaValidator: SAFE_FIELDS enforcement, NDJSON and optional Parquet output.

The canonical collection format is NDJSON (SCRAPERS.md § Output contract).
``pyarrow`` is used for the typed Arrow schema and for the optional Parquet
analytics export of the same allowlist.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from scrapers.base import SAFE_FIELDS, NormalizedRecord


class SchemaValidator:
    """Enforces the SAFE_FIELDS allowlist on every record that is written."""

    def __init__(self, allowlist: frozenset[str] = SAFE_FIELDS) -> None:
        self.allowlist = allowlist

    def validate(self, record: NormalizedRecord) -> NormalizedRecord:
        """Reject any record whose serialized form carries an out-of-allowlist field."""
        extra = set(record.model_dump(mode="json")) - self.allowlist
        if extra:
            raise ValueError(f"fields outside SAFE_FIELDS allowlist: {sorted(extra)}")
        return record

    def write_ndjson(self, rows: Iterable[NormalizedRecord], path: Path) -> int:
        """Write one JSON object per line; returns the number of lines written."""
        count = 0
        with path.open("w", encoding="utf-8") as handle:
            for record in rows:
                validated = self.validate(record)
                handle.write(json.dumps(validated.model_dump_ndjson(), ensure_ascii=False) + "\n")
                count += 1
        return count

    def arrow_schema(self) -> pa.Schema:
        """Typed Arrow schema over the allowlist (skill_mappings as JSON strings)."""
        fields = [
            pa.field(name, pa.string())
            for name in sorted(self.allowlist - {"number_of_vacancies", "skill_mappings"})
        ]
        fields.append(pa.field("number_of_vacancies", pa.int64()))
        fields.append(pa.field("skill_mappings", pa.list_(pa.string())))
        return pa.schema(fields)

    def write_parquet(self, rows: Iterable[NormalizedRecord], path: Path) -> int:
        """Write the allowlist as a Parquet table; returns the number of rows."""
        table_rows: list[dict[str, Any]] = []
        count = 0
        for record in rows:
            validated = self.validate(record)
            dumped = validated.model_dump(mode="json")
            dumped["skill_mappings"] = [
                json.dumps(mapping, ensure_ascii=False) for mapping in dumped["skill_mappings"]
            ]
            table_rows.append(dumped)
            count += 1
        table = pa.Table.from_pylist(table_rows, schema=self.arrow_schema())
        pq.write_table(table, path)
        return count
