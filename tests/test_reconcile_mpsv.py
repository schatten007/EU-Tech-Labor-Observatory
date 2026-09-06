"""Unit tests for the MPSV delta reconciliation (closures, removed_at stamps)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scrapers.base import utc_iso
from scrapers.reconcile_mpsv import (
    ClosureRecord,
    ReconcileResult,
    find_sweep_dirs,
    load_expirace,
    load_source_ids,
    main,
    reconcile,
)


def sid(n: int) -> str:
    return f"{n:064x}"


def write_partition(
    root: Path,
    sweep: str,
    observed: str,
    source_ids: list[str],
    meta: dict[str, str] | None = None,
) -> Path:
    base = root / "raw" / "collections" / "mpsv" / "cz-all-active"
    partition = base / sweep
    partition.mkdir(parents=True, exist_ok=True)
    with (partition / "observations.ndjson").open("w", encoding="utf-8") as handle:
        for source_id in source_ids:
            handle.write(json.dumps({"source_id": source_id}) + "\n")
    (partition / "manifest.json").write_text(
        json.dumps({"observed_at": observed, "row_count": len(source_ids)}), encoding="utf-8"
    )
    if meta:
        with (partition / "meta.ndjson").open("w", encoding="utf-8") as handle:
            for source_id, expirace in sorted(meta.items()):
                handle.write(json.dumps({"source_id": source_id, "expirace": expirace}) + "\n")
    return partition


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def closure_rows(partition: Path) -> list[dict[str, Any]]:
    lines = (partition / "closures.ndjson").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_added_closed_unchanged_and_closures_written(tmp_path: Path) -> None:
    older = write_partition(
        tmp_path, "20260821T000000Z", "2026-08-21T00:00:00Z", [sid(1), sid(2), sid(3)]
    )
    newer = write_partition(
        tmp_path, "20260822T000000Z", "2026-08-22T00:00:00Z", [sid(1), sid(2), sid(4)]
    )

    result = reconcile(
        older,
        newer,
        older_observed_at=parse_iso("2026-08-21T00:00:00Z"),
        newer_observed_at=parse_iso("2026-08-22T00:00:00Z"),
    )

    assert result.older_sweep_id == "20260821T000000Z"
    assert result.newer_sweep_id == "20260822T000000Z"
    assert result.added == {sid(4)}
    assert result.closed == {sid(3)}
    assert result.unchanged == {sid(1), sid(2)}
    assert result.integrity_ok

    rows = closure_rows(newer)
    assert len(rows) == 1
    assert rows[0]["source_id"] == sid(3)
    assert rows[0]["removed_at"] == "2026-08-22T00:00:00Z"
    assert rows[0]["source"] == "mpsv"
    assert rows[0]["scope_id"] == "cz-all-active"
    assert rows[0]["sweep_id"] == "20260822T000000Z"


def test_removed_at_prefers_source_reported_expirace(tmp_path: Path) -> None:
    older = write_partition(
        tmp_path,
        "20260821T000000Z",
        "2026-08-21T00:00:00Z",
        [sid(1), sid(3)],
        meta={sid(3): "2026-08-21"},
    )
    newer = write_partition(tmp_path, "20260822T000000Z", "2026-08-22T00:00:00Z", [sid(1)])

    result = reconcile(
        older,
        newer,
        older_observed_at=parse_iso("2026-08-21T00:00:00Z"),
        newer_observed_at=parse_iso("2026-08-22T00:00:00Z"),
    )

    rows = closure_rows(newer)
    assert rows[0]["source_id"] == sid(3)
    assert rows[0]["removed_at"] == "2026-08-21T00:00:00Z"
    assert result.closed == {sid(3)}
    assert result.integrity_ok


def test_expirace_outside_window_falls_back_to_observed_at(tmp_path: Path) -> None:
    older = write_partition(
        tmp_path,
        "20260821T000000Z",
        "2026-08-21T00:00:00Z",
        [sid(1), sid(3)],
        meta={sid(3): "2026-08-20"},
    )
    newer = write_partition(tmp_path, "20260822T000000Z", "2026-08-22T00:00:00Z", [sid(1)])

    reconcile(
        older,
        newer,
        older_observed_at=parse_iso("2026-08-21T00:00:00Z"),
        newer_observed_at=parse_iso("2026-08-22T00:00:00Z"),
    )

    rows = closure_rows(newer)
    assert rows[0]["removed_at"] == "2026-08-22T00:00:00Z"


def test_closures_are_hmac_only_and_strict_subset(tmp_path: Path) -> None:
    older = write_partition(tmp_path, "A", "2026-08-21T00:00:00Z", [sid(9), sid(8)])
    newer = write_partition(tmp_path, "B", "2026-08-22T00:00:00Z", [sid(9)])
    reconcile(
        older,
        newer,
        older_observed_at=parse_iso("2026-08-21T00:00:00Z"),
        newer_observed_at=parse_iso("2026-08-22T00:00:00Z"),
    )

    rows = closure_rows(newer)
    assert len(rows) == 1
    assert set(rows[0]) == {"source_id", "removed_at", "source", "scope_id", "sweep_id"}
    assert len(rows[0]["source_id"]) == 64


def test_load_source_ids_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "observations.ndjson"
    lines = json.dumps({"source_id": sid(1)}) + "\n\n" + json.dumps({"source_id": sid(2)}) + "\n"
    path.write_text(lines)
    assert load_source_ids(path) == {sid(1), sid(2)}


def test_load_expirace_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_expirace(tmp_path / "meta.ndjson") == {}


def test_find_sweep_dirs_orders_by_sweep_id(tmp_path: Path) -> None:
    write_partition(tmp_path, "20260822T000000Z", "2026-08-22T00:00:00Z", [sid(1)])
    write_partition(tmp_path, "20260821T000000Z", "2026-08-21T00:00:00Z", [sid(1)])
    write_partition(tmp_path, "20260820T000000Z", "2026-08-20T00:00:00Z", [sid(1)])

    dirs = find_sweep_dirs(tmp_path)
    assert [d.name for d in dirs] == [
        "20260820T000000Z",
        "20260821T000000Z",
        "20260822T000000Z",
    ]


def test_reconcile_result_integrity_arithmetic() -> None:
    result = ReconcileResult(
        older_sweep_id="A",
        newer_sweep_id="B",
        older_total=4,
        newer_total=4,
        added={sid(4)},
        closed={sid(3)},
        unchanged={sid(1), sid(2), sid(3)},
    )
    assert result.integrity_ok

    broken = ReconcileResult(
        older_sweep_id="A",
        newer_sweep_id="B",
        older_total=5,
        newer_total=4,
        added={sid(4)},
        closed={sid(3)},
        unchanged={sid(1), sid(2)},
    )
    assert not broken.integrity_ok


def test_closure_record_removed_at_serializes_utc_iso() -> None:
    record = ClosureRecord(
        source_id=sid(7),
        removed_at=datetime(2026, 8, 21, tzinfo=UTC),
        sweep_id="B",
    )
    assert utc_iso(record.removed_at) == "2026-08-21T00:00:00Z"


def test_main_requires_two_sweeps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["reconcile_mpsv", "--root", str(tmp_path)])
    assert main() == 1

    write_partition(tmp_path, "20260822T000000Z", "2026-08-22T00:00:00Z", [sid(1)])
    assert main() == 1
