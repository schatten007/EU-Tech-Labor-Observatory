"""CLI entrypoint for collector sweeps.

Usage:
    python main.py --source pl --date 2026-08-21
    python main.py --source cz --date 2026-08-22
    python main.py --source pl --date 2026-08-21 --max-pages 1   # canary

Writes ``data/raw/collections/<source>/<scope_id>/<sweep_id>/`` with
``observations.ndjson`` and ``manifest.json`` per SCRAPERS.md § Output contract.
The MPSV collector additionally writes ``meta.ndjson`` (HMAC source_id ->
source-reported ``expirace``) used by ``scrapers.reconcile_mpsv`` to stamp
``removed_at`` on closed postings.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from scrapers.base import BaseCollector, SweepWriter, utc_iso
from scrapers.czech_mpsv import (
    MPSV_ACCESS_METHOD,
    MPSV_COVERAGE_LIMITATIONS,
    MPSV_FRESHNESS_THRESHOLD_HOURS,
    MPSV_LICENCE_REFERENCE,
    MPSV_SCOPE_ID,
    MPSV_SCOPE_PARAMS,
    MPSV_SOURCE_VERSION,
    MPSVCollector,
    crosswalk_reference_hashes,
)
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
DEFAULT_REFERENCE = Path("data/reference")


@dataclass(frozen=True)
class SourceConfig:
    slug: str
    scope_id: str
    scope_params: Mapping[str, object]
    source_version: str
    licence_reference: str
    access_method: str
    expected_country: str
    freshness_threshold_hours: int
    coverage_limitations: str
    reference_hashes: str
    build: Callable[..., BaseCollector]


def _poland(
    scope_id: str,
    sweep_id: str,
    observed_at: _dt.datetime,
    hmac_key: bytes,
    max_pages: int | None,
    **_: object,
) -> BaseCollector:
    return PolandCollector(
        scope_id=scope_id,
        sweep_id=sweep_id,
        observed_at=observed_at,
        hmac_key=hmac_key,
        max_pages=max_pages,
    )


def _czech(
    scope_id: str,
    sweep_id: str,
    observed_at: _dt.datetime,
    hmac_key: bytes,
    max_pages: int | None,
    **_: object,
) -> BaseCollector:
    if max_pages is not None and max_pages != 1:
        raise SystemExit("--max-pages is invalid for mpsv: the dump is a single request")
    return MPSVCollector(
        scope_id=scope_id,
        sweep_id=sweep_id,
        observed_at=observed_at,
        hmac_key=hmac_key,
        reference_dir=DEFAULT_REFERENCE,
    )


def source_config(source: str) -> SourceConfig:
    """Manifest constants and collector factory per source slug."""
    if source in ("cbop", "pl"):
        return SourceConfig(
            slug="cbop",
            scope_id=CBOP_SCOPE_ID,
            scope_params=CBOP_SCOPE_PARAMS,
            source_version=CBOP_SOURCE_VERSION,
            licence_reference=CBOP_LICENCE_REFERENCE,
            access_method=CBOP_ACCESS_METHOD,
            expected_country="PL",
            freshness_threshold_hours=CBOP_FRESHNESS_THRESHOLD_HOURS,
            coverage_limitations=CBOP_COVERAGE_LIMITATIONS,
            reference_hashes="",
            build=_poland,
        )
    return SourceConfig(
        slug="mpsv",
        scope_id=MPSV_SCOPE_ID,
        scope_params=MPSV_SCOPE_PARAMS,
        source_version=MPSV_SOURCE_VERSION,
        licence_reference=MPSV_LICENCE_REFERENCE,
        access_method=MPSV_ACCESS_METHOD,
        expected_country="CZ",
        freshness_threshold_hours=MPSV_FRESHNESS_THRESHOLD_HOURS,
        coverage_limitations=MPSV_COVERAGE_LIMITATIONS,
        reference_hashes=crosswalk_reference_hashes(DEFAULT_REFERENCE),
        build=_czech,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a collector sweep")
    parser.add_argument(
        "--source",
        choices=("cbop", "pl", "mpsv", "cz"),
        default="pl",
        help="source slug (pl/cbop = CBOP/ePraca Poland; cz/mpsv = Úřad práce Czechia)",
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


def build_collector(
    config: SourceConfig,
    *,
    scope_id: str,
    sweep_id: str,
    observed_at: _dt.datetime,
    hmac_key: bytes,
    max_pages: int | None,
) -> BaseCollector:
    return config.build(
        scope_id=scope_id,
        sweep_id=sweep_id,
        observed_at=observed_at,
        hmac_key=hmac_key,
        max_pages=max_pages,
    )


def write_expirace_meta(partition: Path, expirace_by_source_id: dict[str, str]) -> None:
    """Persist HMAC source_id -> expirace for the reconciliation step."""
    if not expirace_by_source_id:
        return
    with (partition / "meta.ndjson").open("w", encoding="utf-8") as handle:
        for source_id in sorted(expirace_by_source_id):
            handle.write(
                json.dumps(
                    {"source_id": source_id, "expirace": expirace_by_source_id[source_id]},
                    ensure_ascii=False,
                )
                + "\n"
            )


async def run_sweep(args: argparse.Namespace) -> int:
    observed_at = _dt.datetime.combine(args.date, _dt.time.min, tzinfo=_dt.UTC)
    # Compact filesystem-safe sweep stamp (colons are invalid in Windows paths).
    sweep_id = observed_at.strftime("%Y%m%dT%H%M%SZ")
    run_id = utc_iso(_dt.datetime.now(_dt.UTC))
    started_at = _dt.datetime.now(_dt.UTC)

    config = source_config(args.source)
    collector = build_collector(
        config,
        scope_id=config.scope_id,
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
        source=config.slug,
        scope_id=config.scope_id,
        scope_params=config.scope_params,
        sweep_id=sweep_id,
        run_id=run_id,
        observed_at=observed_at,
        started_at=started_at,
        rows=rows,
        expected_pages=collector.total_pages,
        completed_pages=collector.completed_pages,
        expected_rows=collector.total_elements,
        hmac_key_version="v1",
        source_version=config.source_version,
        licence_reference=config.licence_reference,
        access_method=config.access_method,
        expected_country=config.expected_country,
        freshness_threshold_hours=config.freshness_threshold_hours,
        coverage_limitations=config.coverage_limitations,
        reference_hashes=config.reference_hashes,
    )

    if isinstance(collector, MPSVCollector):
        write_expirace_meta(partition, collector.expirace_by_source_id)

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
