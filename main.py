"""CLI entrypoint for collector sweeps.

Usage:
    python main.py --source pl --date 2026-08-21
    python main.py --source cz --date 2026-08-22
    python main.py --source ft --date 2026-08-22 --max-pages 120
    python main.py --source be --date 2026-08-22 --max-pages 500
    python main.py --source no --date 2026-08-23 --since 3 --max-details 1500
    python main.py --source no --date 2026-08-23            # daily poll (cursor)
    python main.py --source fi --date 2026-08-23 --max-rows 100  # TMT smoke pull
    python main.py --source pl --date 2026-08-21 --max-pages 1   # canary

Writes ``data/raw/collections/<source>/<scope_id>/<sweep_id>/`` with
``observations.ndjson`` and ``manifest.json`` per SCRAPERS.md § Output contract.
The MPSV collector additionally writes ``meta.ndjson`` (HMAC source_id ->
source-reported ``expirace``) used by ``scrapers.reconcile_mpsv`` to stamp
``removed_at`` on closed postings. NAV needs no such pass: its feed reports
closures itself, and the collector persists a poll cursor in
``data/state/nav_feed_cursor.json`` so the next daily sweep resumes. Finland's
TMT collector reports closures itself too (``metadata.archived``) and persists a
client-side watermark in ``data/state/finland_tmt_cursor.json``, because the P67
stream has no server-side cursor.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from scrapers.adzuna import (
    ADZUNA_ADAPTERS,
    ADZUNA_DE,
    AdzunaCollector,
    CountryAdapter,
    adzuna_credentials,
)
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
from scrapers.finland_tmt import (
    TMT_ACCESS_METHOD,
    TMT_COVERAGE_LIMITATIONS,
    TMT_FRESHNESS_THRESHOLD_HOURS,
    TMT_LICENCE_REFERENCE,
    TMT_SCOPE_ID,
    TMT_SCOPE_PARAMS,
    TMT_SOURCE_VERSION,
    TMT_STATUS_ARCHIVED,
    TMT_STATUS_PUBLISHED,
    FinlandTMTCollector,
    tmt_credentials,
)
from scrapers.finland_tmt import (
    crosswalk_reference_hashes as tmt_crosswalk_reference_hashes,
)
from scrapers.france_travail import (
    FT_ACCESS_METHOD,
    FT_COVERAGE_LIMITATIONS,
    FT_FRESHNESS_THRESHOLD_HOURS,
    FT_LICENCE_REFERENCE,
    FT_SCOPE_ID,
    FT_SCOPE_PARAMS,
    FT_SOURCE_VERSION,
    FranceTravailCollector,
    france_travail_credentials,
)
from scrapers.france_travail import (
    crosswalk_reference_hashes as ft_crosswalk_reference_hashes,
)
from scrapers.nav_norway import (
    NAV_ACCESS_METHOD,
    NAV_COVERAGE_LIMITATIONS,
    NAV_FRESHNESS_THRESHOLD_HOURS,
    NAV_ITEMS_PER_PAGE,
    NAV_LICENCE_REFERENCE,
    NAV_SCOPE_ID,
    NAV_SCOPE_PARAMS,
    NAV_SOURCE_VERSION,
    NAVFeedCollector,
)
from scrapers.nav_norway import (
    crosswalk_reference_hashes as nav_crosswalk_reference_hashes,
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
from scrapers.vdab import (
    VDAB_ACCESS_METHOD,
    VDAB_ADVERTISED_FLANDERS_STOCK,
    VDAB_COVERAGE_LIMITATIONS,
    VDAB_FRESHNESS_THRESHOLD_HOURS,
    VDAB_LICENCE_REFERENCE,
    VDAB_SCOPE_ID,
    VDAB_SCOPE_PARAMS,
    VDAB_SOURCE_VERSION,
    VDABCollector,
)
from scrapers.vdab import (
    crosswalk_reference_hashes as vdab_crosswalk_reference_hashes,
)

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


def _france_travail(
    scope_id: str,
    sweep_id: str,
    observed_at: _dt.datetime,
    hmac_key: bytes,
    max_pages: int | None,
    **_: object,
) -> BaseCollector:
    client_id, client_secret = france_travail_credentials()
    return FranceTravailCollector(
        scope_id=scope_id,
        sweep_id=sweep_id,
        observed_at=observed_at,
        hmac_key=hmac_key,
        client_id=client_id,
        client_secret=client_secret,
        reference_dir=DEFAULT_REFERENCE,
        max_pages=max_pages,
    )


def _vdab(
    scope_id: str,
    sweep_id: str,
    observed_at: _dt.datetime,
    hmac_key: bytes,
    max_pages: int | None,
    **_: object,
) -> BaseCollector:
    return VDABCollector(
        scope_id=scope_id,
        sweep_id=sweep_id,
        observed_at=observed_at,
        hmac_key=hmac_key,
        reference_dir=DEFAULT_REFERENCE,
        max_pages=max_pages,
    )


def _nav(
    scope_id: str,
    sweep_id: str,
    observed_at: _dt.datetime,
    hmac_key: bytes,
    max_pages: int | None,
    since_days: int | None = None,
    max_details: int | None = None,
    use_cursor: bool = True,
    **_: object,
) -> BaseCollector:
    return NAVFeedCollector(
        scope_id=scope_id,
        sweep_id=sweep_id,
        observed_at=observed_at,
        hmac_key=hmac_key,
        reference_dir=DEFAULT_REFERENCE,
        since_days=since_days,
        max_pages=max_pages,
        max_details=max_details,
        use_cursor=use_cursor,
    )


def _finland_tmt(
    scope_id: str,
    sweep_id: str,
    observed_at: _dt.datetime,
    hmac_key: bytes,
    max_pages: int | None,
    max_rows: int | None = None,
    only_status: str = TMT_STATUS_PUBLISHED,
    use_cursor: bool = True,
    **_: object,
) -> BaseCollector:
    if max_pages is not None:
        raise SystemExit(
            "--max-pages is invalid for tmt: the P67 API has no pagination "
            "(one POST streams a whole result set). Use --max-rows instead."
        )
    subscription_key, bearer_token = tmt_credentials()
    return FinlandTMTCollector(
        scope_id=scope_id,
        sweep_id=sweep_id,
        observed_at=observed_at,
        hmac_key=hmac_key,
        subscription_key=subscription_key,
        bearer_token=bearer_token,
        reference_dir=DEFAULT_REFERENCE,
        only_status=only_status,
        max_rows=max_rows,
        use_cursor=use_cursor,
    )


def _adzuna(adapter: CountryAdapter) -> Callable[..., BaseCollector]:
    """Factory for an Adzuna collector bound to one country adapter."""

    def build(
        scope_id: str,
        sweep_id: str,
        observed_at: _dt.datetime,
        hmac_key: bytes,
        max_pages: int | None,
        **_: object,
    ) -> BaseCollector:
        app_id, app_key = adzuna_credentials()
        return AdzunaCollector(
            scope_id=scope_id,
            sweep_id=sweep_id,
            observed_at=observed_at,
            hmac_key=hmac_key,
            adapter=adapter,
            app_id=app_id,
            app_key=app_key,
            max_pages=max_pages,
        )

    return build


def source_config(source: str, country: str = "de") -> SourceConfig:
    """Manifest constants and collector factory per source slug.

    ``country`` selects the Adzuna ``CountryAdapter`` (``de`` default,
    ``nl`` etc.); it is ignored for single-country sources.
    """
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
    if source == "adzuna":
        adapter = ADZUNA_ADAPTERS.get(country, ADZUNA_DE)
        return SourceConfig(
            slug="adzuna",
            scope_id=adapter.scope_id,
            scope_params=adapter.scope_params,
            source_version=adapter.source_version,
            licence_reference=adapter.licence_reference,
            access_method=adapter.access_method,
            expected_country=adapter.expected_country,
            freshness_threshold_hours=adapter.freshness_threshold_hours,
            coverage_limitations=adapter.coverage_limitations,
            reference_hashes="",
            build=_adzuna(adapter),
        )
    if source in ("francetravail", "ft", "fr"):
        return SourceConfig(
            slug="francetravail",
            scope_id=FT_SCOPE_ID,
            scope_params=FT_SCOPE_PARAMS,
            source_version=FT_SOURCE_VERSION,
            licence_reference=FT_LICENCE_REFERENCE,
            access_method=FT_ACCESS_METHOD,
            expected_country="FR",
            freshness_threshold_hours=FT_FRESHNESS_THRESHOLD_HOURS,
            coverage_limitations=FT_COVERAGE_LIMITATIONS,
            reference_hashes=ft_crosswalk_reference_hashes(DEFAULT_REFERENCE),
            build=_france_travail,
        )
    if source in ("vdab", "be"):
        return SourceConfig(
            slug="vdab",
            scope_id=VDAB_SCOPE_ID,
            scope_params=VDAB_SCOPE_PARAMS,
            source_version=VDAB_SOURCE_VERSION,
            licence_reference=VDAB_LICENCE_REFERENCE,
            access_method=VDAB_ACCESS_METHOD,
            expected_country="BE",
            freshness_threshold_hours=VDAB_FRESHNESS_THRESHOLD_HOURS,
            coverage_limitations=VDAB_COVERAGE_LIMITATIONS,
            reference_hashes=vdab_crosswalk_reference_hashes(DEFAULT_REFERENCE),
            build=_vdab,
        )
    if source in ("nav", "no"):
        return SourceConfig(
            slug="nav",
            scope_id=NAV_SCOPE_ID,
            scope_params=NAV_SCOPE_PARAMS,
            source_version=NAV_SOURCE_VERSION,
            licence_reference=NAV_LICENCE_REFERENCE,
            access_method=NAV_ACCESS_METHOD,
            expected_country="NO",
            freshness_threshold_hours=NAV_FRESHNESS_THRESHOLD_HOURS,
            coverage_limitations=NAV_COVERAGE_LIMITATIONS,
            reference_hashes=nav_crosswalk_reference_hashes(DEFAULT_REFERENCE),
            build=_nav,
        )
    if source in ("tmt", "finland", "fi"):
        return SourceConfig(
            slug="tmt",
            scope_id=TMT_SCOPE_ID,
            scope_params=TMT_SCOPE_PARAMS,
            source_version=TMT_SOURCE_VERSION,
            licence_reference=TMT_LICENCE_REFERENCE,
            access_method=TMT_ACCESS_METHOD,
            expected_country="FI",
            freshness_threshold_hours=TMT_FRESHNESS_THRESHOLD_HOURS,
            coverage_limitations=TMT_COVERAGE_LIMITATIONS,
            reference_hashes=tmt_crosswalk_reference_hashes(DEFAULT_REFERENCE),
            build=_finland_tmt,
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
        choices=(
            "cbop",
            "pl",
            "mpsv",
            "cz",
            "adzuna",
            "francetravail",
            "ft",
            "fr",
            "vdab",
            "be",
            "nav",
            "no",
            "tmt",
            "finland",
            "fi",
        ),
        default="pl",
        help="source slug (pl/cbop = CBOP/ePraca Poland; cz/mpsv = Úřad práce "
        "Czechia; adzuna = Adzuna multi-country API; ft/fr/francetravail = "
        "France Travail Offres d'emploi v2; be/vdab = VDAB public job-search "
        "website, Belgium/Flanders; no/nav = NAV stillings-feed, Norway; "
        "fi/tmt/finland = Työmarkkinatori jobposting search API, Finland)",
    )
    parser.add_argument(
        "--country",
        choices=tuple(ADZUNA_ADAPTERS),
        default="de",
        help="Adzuna country adapter (de, nl, ...); ignored for other sources",
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
    parser.add_argument(
        "--since",
        type=int,
        default=None,
        help="NAV only: If-Modified-Since backfill window in days (default: resume "
        "from the persisted cursor, else 7 days; capped at ~190 because an ad is "
        "never active longer than 6 months). Passing it forces a fresh seek.",
    )
    parser.add_argument(
        "--max-details",
        type=int,
        default=None,
        help="NAV only: cap the ad-detail requests (1 paced request each, so this "
        "is the sweep's wall-clock and ESCO-coverage dial)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="NAV/TMT only: ignore the persisted poll cursor or watermark instead of resuming it",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Työmarkkinatori only: stop the NDJSON stream after N postings "
        "(the API has no pagination, so this is the smoke-pull dial, e.g. 100)",
    )
    parser.add_argument(
        "--status",
        choices=(TMT_STATUS_PUBLISHED, TMT_STATUS_ARCHIVED),
        default=TMT_STATUS_PUBLISHED,
        help="Työmarkkinatori only: FiltersV2 onlyStatus — PUBLISHED is the "
        "active set, ARCHIVED is the closed set",
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
    since_days: int | None = None,
    max_details: int | None = None,
    use_cursor: bool = True,
    max_rows: int | None = None,
    only_status: str = TMT_STATUS_PUBLISHED,
) -> BaseCollector:
    """Build the configured collector.

    ``since_days`` / ``max_details`` are NAV's feed-window and detail-budget
    dials, ``max_rows`` / ``only_status`` are Työmarkkinatori's stream dials, and
    ``use_cursor`` is shared by both cursor-bearing sources; every other source's
    factory ignores them.
    """
    return config.build(
        scope_id=scope_id,
        sweep_id=sweep_id,
        observed_at=observed_at,
        hmac_key=hmac_key,
        max_pages=max_pages,
        since_days=since_days,
        max_details=max_details,
        use_cursor=use_cursor,
        max_rows=max_rows,
        only_status=only_status,
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

    config = source_config(args.source, country=args.country)
    collector = build_collector(
        config,
        scope_id=config.scope_id,
        sweep_id=sweep_id,
        observed_at=observed_at,
        hmac_key=load_hmac_key(),
        max_pages=args.max_pages,
        since_days=args.since,
        max_details=args.max_details,
        use_cursor=not args.fresh,
        max_rows=args.max_rows,
        only_status=args.status,
    )

    rows = []
    async with collector:
        async for record in collector.collect():
            rows.append(record)

    # Append the live advertised count to coverage_limitations (Adzuna).
    coverage = config.coverage_limitations
    if isinstance(collector, AdzunaCollector) and collector.advertised_count is not None:
        coverage += (
            f" Advertised count at sweep: {collector.advertised_count} active listings "
            f"for {collector.expected_country}."
        )
    if isinstance(collector, FranceTravailCollector):
        coverage += (
            f" Sweep budget: {collector.completed_pages} windows fetched "
            f"({collector.planned_pages} implied by the advertised segment totals), "
            f"{collector.token_requests} token request(s)."
        )
        if collector.advertised_count is not None:
            coverage += (
                f" Advertised national stock at sweep: {collector.advertised_count} "
                "active offers (FR)."
            )

    if isinstance(collector, VDABCollector):
        coverage += (
            f" Sweep breadth: {collector.completed_pages}/{collector.total_pages} landing pages "
            f"fetched (of {collector.landing_pages_available} Flemish-postcode landing pages "
            f"discovered in the keyword sitemaps), {collector.failed_pages} non-200; "
            f"{collector.tiles_seen} tiles parsed, {collector.duplicates_dropped} cross-page "
            f"duplicates dropped on HMAC source_id, {collector.tiles_without_id} tiles without a "
            f"resolvable id. Rows collected: {len(rows)} of the "
            f"{VDAB_ADVERTISED_FLANDERS_STOCK} active Flemish vacancies the search page "
            "advertises — a breadth sample, not a complete snapshot."
        )
        if collector.max_advertised_total is not None:
            coverage += (
                f" Largest per-segment total advertised by a fetched landing page: "
                f"{collector.max_advertised_total} jobs."
            )

    if isinstance(collector, NAVFeedCollector):
        coverage += (
            f" Sweep window: {collector.completed_pages} feed page(s) at "
            f"{NAV_ITEMS_PER_PAGE} events each"
            + (
                " resumed from the persisted cursor"
                if collector.resumed_from_cursor
                else f" seeked with If-Modified-Since {collector.since_header}"
            )
            + f" ({collector.pages_unchanged} answered 304 Not Modified), "
            f"{collector.events_seen} feed events folded to {len(rows)} rows "
            f"({collector.rows_active} ACTIVE / {collector.rows_inactive} INACTIVE, "
            f"{collector.rows_removed} with a source-reported removed_at); "
            f"{collector.detail_requests} ad-detail request(s) of a "
            f"{collector.detail_budget} budget "
            f"({collector.details_with_content} with ad_content, "
            f"{collector.details_masked} content-masked, "
            f"{collector.details_missing} no longer served, "
            f"{collector.details_failed} abandoned after 5xx retries), "
            f"{collector.rows_with_esco} rows carry an ESCO occupation URI; "
            f"{collector.token_requests} token request(s), "
            f"{collector.token_refreshes} token rotation(s) handled mid-sweep."
        )

    if isinstance(collector, FinlandTMTCollector):
        coverage += (
            f" Sweep window: {collector.streams_completed} NDJSON stream(s) with filters "
            f"{json.dumps(collector.filters(), sort_keys=True)}"
            + (
                f" resumed from the persisted watermark {collector.modified_from_used}"
                if collector.modified_from_used
                else " with no watermark (full result set)"
            )
            + f"; {collector.lines_seen} stream line(s) → {len(rows)} rows "
            f"({collector.malformed_lines} malformed line(s) skipped, "
            f"{collector.rows_without_id} without metadata.externalId, "
            f"{collector.duplicates_dropped} duplicate(s) dropped on HMAC source_id); "
            f"{collector.rows_with_esco_occupation} rows carry a native ESCO occupation "
            f"URI, {collector.rows_with_skills} rows carry "
            f"{collector.skill_elements} skill_mappings element(s), "
            f"{collector.rows_removed} rows carry a source-reported removed_at; "
            f"{collector.token_refreshes} bearer refresh(es)."
        )
        if collector.truncated_by_budget:
            coverage += (
                " TRUNCATED: the --max-rows budget stopped the stream before its end, "
                "so this partition is a sample and no watermark was persisted."
            )
        if collector.rate_limit:
            coverage += f" RateLimit headers at sweep: {collector.rate_limit}."
        if collector.watermark:
            coverage += f" Watermark (max metadata.lastModified): {collector.watermark}."

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
        coverage_limitations=coverage,
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
