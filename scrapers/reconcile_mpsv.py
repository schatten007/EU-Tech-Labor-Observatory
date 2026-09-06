"""MPSV delta reconciliation — stamps ``removed_at`` on closed postings.

The MPSV dump is the *active set*: a posting disappears from the dump when it
closes, and the source emits no removal event. This module compares two
consecutive daily partitions by **HMAC ``source_id`` only** (no native ids, no
PII ever touch the comparison) and writes ``closures.ndjson`` into the newer
partition:

    {
      "source_id": "<64-hex HMAC>",
      "removed_at": "2026-08-22T00:00:00Z",
      "source": "mpsv",
      "scope_id": "cz-all-active",
      "sweep_id": "<newer sweep>"
    }

``removed_at`` is the source-reported ``expirace`` (publication deadline) when
the older partition carried one that fell inside the window, otherwise the
newer sweep's ``observed_at`` (inferred from absence). Every field is a strict
subset of SAFE_FIELDS.

CLI (after at least two daily sweeps exist):

    python -m scrapers.reconcile_mpsv            # --root data (default)
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from scrapers.base import utc_iso

MPSV_SOURCE = "mpsv"
MPSV_SCOPE = "cz-all-active"


class ClosureRecord(BaseModel):
    """One closed posting: HMAC source_id plus the removal timestamp."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    removed_at: datetime
    source: str = MPSV_SOURCE
    scope_id: str = MPSV_SCOPE
    sweep_id: str


class ReconcileResult(BaseModel):
    """Outcome of comparing two consecutive sweeps."""

    older_sweep_id: str
    newer_sweep_id: str
    older_total: int
    newer_total: int
    added: set[str]
    closed: set[str]
    unchanged: set[str]

    @property
    def integrity_ok(self) -> bool:
        """Newer == unchanged + added, older == unchanged + closed."""
        older_ok = self.older_total == len(self.unchanged) + len(self.closed)
        newer_ok = self.newer_total == len(self.unchanged) + len(self.added)
        return older_ok and newer_ok


def load_source_ids(ndjson_path: Path) -> set[str]:
    """All ``source_id`` values in one sweep's observations.ndjson."""
    source_ids: set[str] = set()
    with ndjson_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            source_ids.add(str(json.loads(line)["source_id"]))
    return source_ids


def load_expirace(meta_path: Path) -> dict[str, str]:
    """``source_id -> expirace`` (YYYY-MM-DD) from the collector's meta.ndjson."""
    if not meta_path.exists():
        return {}
    result: dict[str, str] = {}
    with meta_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("expirace"):
                result[str(row["source_id"])] = str(row["expirace"])
    return result


def _manifest_observed_at(partition: Path) -> datetime:
    manifest_path = partition / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing manifest in partition {partition}")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return datetime.fromisoformat(str(raw["observed_at"]).replace("Z", "+00:00"))


def reconcile(
    older: Path,
    newer: Path,
    *,
    older_observed_at: datetime,
    newer_observed_at: datetime,
) -> ReconcileResult:
    """Compare two partitions and resolve closure timestamps."""
    older_ids = load_source_ids(older / "observations.ndjson")
    newer_ids = load_source_ids(newer / "observations.ndjson")
    older_expirace = load_expirace(older / "meta.ndjson")

    unchanged = older_ids & newer_ids
    added = newer_ids - older_ids
    closed = older_ids - newer_ids

    closures: list[ClosureRecord] = []
    for source_id in sorted(closed):
        removed_at: datetime
        raw_expirace = older_expirace.get(source_id)
        if raw_expirace:
            expirace = datetime.strptime(raw_expirace, "%Y-%m-%d").replace(tzinfo=UTC)
            if older_observed_at <= expirace <= newer_observed_at:
                removed_at = expirace
            else:
                removed_at = newer_observed_at
        else:
            removed_at = newer_observed_at
        closures.append(
            ClosureRecord(
                source_id=source_id,
                removed_at=removed_at,
                sweep_id=newer.name,
            )
        )

    write_closures(newer, closures)
    return ReconcileResult(
        older_sweep_id=older.name,
        newer_sweep_id=newer.name,
        older_total=len(older_ids),
        newer_total=len(newer_ids),
        added=added,
        closed=closed,
        unchanged=unchanged,
    )


def write_closures(partition: Path, closures: list[ClosureRecord]) -> int:
    """Write ``closures.ndjson`` next to the sweep's observations.ndjson."""
    with (partition / "closures.ndjson").open("w", encoding="utf-8") as handle:
        for record in sorted(closures, key=lambda c: c.source_id):
            payload = record.model_dump(mode="json")
            payload["removed_at"] = utc_iso(record.removed_at)
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return len(closures)


def find_sweep_dirs(root: Path) -> list[Path]:
    """Partitions under ``root/raw/collections/mpsv/cz-all-active/`` by sweep id."""
    base = root / "raw" / "collections" / MPSV_SOURCE / MPSV_SCOPE
    if not base.exists():
        return []
    return sorted([p for p in base.iterdir() if p.is_dir()], key=lambda p: p.name)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile the two most recent MPSV sweeps and stamp closures"
    )
    parser.add_argument("--root", type=Path, default=Path("data"))
    args = parser.parse_args()

    partitions = find_sweep_dirs(args.root)
    if len(partitions) < 2:
        print(f"need at least two consecutive MPSV sweeps (found {len(partitions)})")
        return 1

    older, newer = partitions[-2], partitions[-1]
    result = reconcile(
        older,
        newer,
        older_observed_at=_manifest_observed_at(older),
        newer_observed_at=_manifest_observed_at(newer),
    )
    print(f"older sweep : {result.older_sweep_id}")
    print(f"newer sweep : {result.newer_sweep_id}")
    print(f"added       : {len(result.added)}")
    print(f"closed      : {len(result.closed)}")
    print(f"unchanged   : {len(result.unchanged)}")
    print(f"integrity   : {'OK' if result.integrity_ok else 'BROKEN'}")
    print(f"closures    : {newer / 'closures.ndjson'}")
    return 0 if result.integrity_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
