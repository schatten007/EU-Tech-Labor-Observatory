"""Unit tests for SweepWriter partition output and manifest reconciliation."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scrapers.base import NormalizedRecord, SweepWriter


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


def write_partition(
    root: Path, rows: list[NormalizedRecord], expected_rows: int, completed_pages: int = 2
) -> dict[str, Any]:
    writer = SweepWriter(root)
    partition = writer.write_partition(
        source="cbop",
        scope_id="pl-all-active",
        scope_params={"country": "PL", "query": "all-active"},
        sweep_id="20260821T000000Z",
        run_id="20260821T120000Z",
        observed_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        started_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 21, 12, 5, tzinfo=UTC),
        rows=rows,
        expected_pages=2,
        completed_pages=completed_pages,
        expected_rows=expected_rows,
        hmac_key_version="v1",
        source_version="portal-api-v3",
        licence_reference="https://creativecommons.org/licenses/by/3.0/pl/",
        access_method="public-api",
        expected_country="PL",
        freshness_threshold_hours=24,
        coverage_limitations="none",
    )
    raw = (partition / "manifest.json").read_text(encoding="utf-8")
    manifest_value: dict[str, Any] = json.loads(raw)
    return manifest_value


def test_complete_partition_when_counts_match(tmp_path: Path) -> None:
    rows = [NormalizedRecord(**base_kwargs()), NormalizedRecord(**base_kwargs(source_id="b" * 64))]
    manifest = write_partition(tmp_path, rows, expected_rows=2)

    assert manifest["status"] == "complete"
    assert manifest["expected_pages"] == manifest["completed_pages"] == 2
    assert manifest["expected_rows"] == manifest["row_count"] == 2
    assert manifest["expected_country"] == "PL"
    assert manifest["approval_status"] == "approved"

    partition = tmp_path / "raw" / "collections" / "cbop" / "pl-all-active" / "20260821T000000Z"
    ndjson = partition / "observations.ndjson"
    assert len(ndjson.read_text(encoding="utf-8").splitlines()) == 2


def test_partial_when_rows_mismatch_expected(tmp_path: Path) -> None:
    rows = [NormalizedRecord(**base_kwargs())]
    manifest = write_partition(tmp_path, rows, expected_rows=2)

    assert manifest["status"] == "partial"
    assert manifest["expected_rows"] == 2
    assert manifest["row_count"] == 1


def test_partial_when_pages_mismatch(tmp_path: Path) -> None:
    rows = [NormalizedRecord(**base_kwargs())]
    manifest = write_partition(tmp_path, rows, expected_rows=1, completed_pages=1)

    assert manifest["status"] == "partial"
    assert manifest["expected_pages"] == 2
    assert manifest["completed_pages"] == 1
