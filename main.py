"""CLI entrypoint for collector sweeps.

Usage:
    python main.py --source pl --date 2026-08-21
    python main.py --source pl --date 2026-08-21 --max-pages 1   # canary

Writes ``data/raw/collections/<source>/<scope_id>/<sweep_id>/`` with
``observations.ndjson`` and ``manifest.json`` per SCRAPERS.md § Output contract.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
from pathlib import Path

from scrapers.base import SweepWriter, utc_iso
from scrapers.poland_cbop import (
    CBOP_ACCESS_METHOD,
    CBOP_COVERAGE_LIMITATIONS,
    CBOP_FRESHNESS_THRESHOLD_HOURS,
    CBOP_LICENCE_REFERENCE,
    CBOP_SCOPE_ID,
    CBOP_SCOPE_PARAMS,
    CBOP_SOURCE_VERSION,
    PolandCollector,
)
from scrapers.sanitize import load_hmac_key
from scrapers.validate import SchemaValidator

DEFAULT_ROOT = Path("data")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a collector sweep")
    parser.add_argument(
        "--source",
        choices=("cbop", "pl"),
        default="pl",
        help="source slug (pl = CBOP/ePraca Poland)",
    )
    parser.add_argument(
        "--date",
        type=_dt.date.fromisoformat,
        default=_dt.date.today(),
        help="sweep date, ISO format (default: today, UTC)",
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="data root (default: data)")
    parser.add_argument(
        "--max-pages", type=int, default=None, help="limit the sweep to N pages (canary mode)"
    )
    parser.add_argument("--parquet", action="store_true", help="also export the sweep as Parquet")
    return parser


async def run_sweep(args: argparse.Namespace) -> int:
    if args.source not in ("cbop", "pl"):
        raise SystemExit(f"unsupported source: {args.source}")

    observed_at = _dt.datetime.combine(args.date, _dt.time.min, tzinfo=_dt.UTC)
    # Compact filesystem-safe sweep stamp (colons are invalid in Windows paths).
    sweep_id = observed_at.strftime("%Y%m%dT%H%M%SZ")
    run_id = utc_iso(_dt.datetime.now(_dt.UTC))
    started_at = _dt.datetime.now(_dt.UTC)

    collector = PolandCollector(
        scope_id=CBOP_SCOPE_ID,
        sweep_id=sweep_id,
        observed_at=observed_at,
        hmac_key=load_hmac_key(),
        max_pages=args.max_pages,
    )

    rows = []
    async with collector:
        async for record in collector.collect():
            rows.append(record)

    validator = SchemaValidator()
    writer = SweepWriter(args.root)
    partition = writer.write_partition(
        source="cbop",
        scope_id=CBOP_SCOPE_ID,
        scope_params=CBOP_SCOPE_PARAMS,
        sweep_id=sweep_id,
        run_id=run_id,
        observed_at=observed_at,
        started_at=started_at,
        rows=rows,
        expected_pages=collector.total_pages,
        completed_pages=collector.completed_pages,
        expected_rows=collector.total_elements,
        hmac_key_version="v1",
        source_version=CBOP_SOURCE_VERSION,
        licence_reference=CBOP_LICENCE_REFERENCE,
        access_method=CBOP_ACCESS_METHOD,
        expected_country="PL",
        freshness_threshold_hours=CBOP_FRESHNESS_THRESHOLD_HOURS,
        coverage_limitations=CBOP_COVERAGE_LIMITATIONS,
    )

    if args.parquet:
        validator.write_parquet(rows, partition / "observations.parquet")

    print(f"partition: {partition}")
    print(f"rows: {len(rows)}  pages: {collector.completed_pages}/{collector.total_pages}")
    print(f"expected_rows: {collector.total_elements}  manifest written (see partition)")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(run_sweep(args))


if __name__ == "__main__":
    raise SystemExit(main())
