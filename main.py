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
from scrapers.ba_jobsuche import (
    BA_ACCESS_METHOD,
    BA_COVERAGE_LIMITATIONS,
    BA_FRESHNESS_THRESHOLD_HOURS,
    BA_LICENCE_REFERENCE,
    BA_SCOPE_ID,
    BA_SCOPE_PARAMS,
    BA_SEGMENTED_SCOPE_ID,
    BA_SEGMENTED_SCOPE_PARAMS,
    BA_SOURCE_VERSION,
    BAJobsucheCollector,
    GermanCrosswalk,
)
from scrapers.ba_jobsuche import (
    crosswalk_reference_hashes as ba_crosswalk_reference_hashes,
)
from scrapers.ba_panel import (
    BA_PANEL_MIN_REGIONS,
    BA_PANEL_SCOPE_ID,
    ba_panel_coverage_limitations,
    ba_panel_scope_params,
    build_panel,
    panel_membership_hash,
    write_panel_regions,
)
from scrapers.ba_segments import SegmentFrontier, build_initial_frontier
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
DEFAULT_STATE = Path("data/state")
BA_FRONTIER_PATH = DEFAULT_STATE / "ba_segment_frontier.json"


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


def _ba_jobsuche(
    scope_id: str,
    sweep_id: str,
    observed_at: _dt.datetime,
    hmac_key: bytes,
    max_pages: int | None,
    **_: object,
) -> BaseCollector:
    return BAJobsucheCollector(
        scope_id=scope_id,
        sweep_id=sweep_id,
        observed_at=observed_at,
        hmac_key=hmac_key,
        reference_dir=DEFAULT_REFERENCE,
        max_pages=max_pages,
    )


def _ba_jobsuche_segmented(
    scope_id: str,
    sweep_id: str,
    observed_at: _dt.datetime,
    hmac_key: bytes,
    max_pages: int | None = None,
    max_segments: int | None = None,
    min_level: int = 0,
    umkreis: int = 0,
    fresh: bool = False,
    **_: object,
) -> BaseCollector:
    crosswalk = GermanCrosswalk(DEFAULT_REFERENCE)
    if fresh or not BA_FRONTIER_PATH.exists():
        frontier = build_initial_frontier(crosswalk, umkreis=umkreis)
        BA_FRONTIER_PATH.parent.mkdir(parents=True, exist_ok=True)
        frontier.save(BA_FRONTIER_PATH)
    else:
        frontier = SegmentFrontier.load(BA_FRONTIER_PATH)
    return BAJobsucheCollector(
        scope_id=scope_id,
        sweep_id=sweep_id,
        observed_at=observed_at,
        hmac_key=hmac_key,
        reference_dir=DEFAULT_REFERENCE,
        frontier=frontier,
        frontier_path=BA_FRONTIER_PATH,
        max_segments=max_segments,
        min_level=min_level,
        umkreis=umkreis,
    )


def _ba_jobsuche_panel(
    scope_id: str,
    sweep_id: str,
    observed_at: _dt.datetime,
    hmac_key: bytes,
    **_: object,
) -> BaseCollector:
    """Frozen NUTS-3 panel (step 2b). The query list is pinned, never adaptive."""
    return BAJobsucheCollector(
        scope_id=scope_id,
        sweep_id=sweep_id,
        observed_at=observed_at,
        hmac_key=hmac_key,
        reference_dir=DEFAULT_REFERENCE,
        panel=build_panel(DEFAULT_REFERENCE),
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


def source_config(
    source: str, country: str = "de", *, segmented: bool = False, panel: bool = False
) -> SourceConfig:
    """Manifest constants and collector factory per source slug.

    ``country`` selects the Adzuna ``CountryAdapter`` (``de`` default,
    ``nl`` etc.); it is ignored for single-country sources. ``segmented``
    switches BA to the Increment 9 ``de-stock-segmented`` scope and frontier
    (**cancelled 2026-08-31, never re-swept**); ``panel`` switches BA to the
    step-2b frozen NUTS-3 panel scope ``de-nuts3-panel``.
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
    if source in ("ba", "ba_jobsuche", "de"):
        if panel:
            built = build_panel(DEFAULT_REFERENCE)
            return SourceConfig(
                slug="ba",
                scope_id=BA_PANEL_SCOPE_ID,
                scope_params=ba_panel_scope_params(built),
                source_version=BA_SOURCE_VERSION,
                licence_reference=BA_LICENCE_REFERENCE,
                access_method=BA_ACCESS_METHOD,
                expected_country="DE",
                freshness_threshold_hours=BA_FRESHNESS_THRESHOLD_HOURS,
                coverage_limitations=ba_panel_coverage_limitations(built),
                reference_hashes=ba_crosswalk_reference_hashes(DEFAULT_REFERENCE),
                build=_ba_jobsuche_panel,
            )
        return SourceConfig(
            slug="ba",
            scope_id=BA_SEGMENTED_SCOPE_ID if segmented else BA_SCOPE_ID,
            scope_params=BA_SEGMENTED_SCOPE_PARAMS if segmented else BA_SCOPE_PARAMS,
            source_version=BA_SOURCE_VERSION,
            licence_reference=BA_LICENCE_REFERENCE,
            access_method=BA_ACCESS_METHOD,
            expected_country="DE",
            freshness_threshold_hours=BA_FRESHNESS_THRESHOLD_HOURS,
            coverage_limitations=BA_COVERAGE_LIMITATIONS,
            reference_hashes=ba_crosswalk_reference_hashes(DEFAULT_REFERENCE),
            build=_ba_jobsuche_segmented if segmented else _ba_jobsuche,
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
            "ba",
            "ba_jobsuche",
            "de",
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
        "Czechia; adzuna = Adzuna multi-country API; ba/ba_jobsuche/de = BA "
        "Jobsuche public website, Germany; ft/fr/francetravail = France Travail "
        "Offres d'emploi v2; be/vdab = VDAB public job-search website, "
        "Belgium/Flanders; no/nav = NAV stillings-feed, Norway; "
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
        "--segmented",
        action="store_true",
        help="BA only: run the segmented regional census (scope de-stock-segmented) "
        "against the resumable frontier at data/state/ba_segment_frontier.json "
        "instead of the single unscoped 10,000-listing window",
    )
    parser.add_argument(
        "--panel",
        action="store_true",
        help="BA only: sweep the frozen NUTS-3 panel (scope de-nuts3-panel, step "
        "2b) — one pinned place query per NUTS-3 region, page-capped, designed "
        "for weekly re-sweep. The query set is a pure function of the pinned "
        "crosswalk, so it is byte-identical across sweeps.",
    )
    parser.add_argument(
        "--max-segments",
        type=int,
        default=None,
        help="BA segmented only: stop after N segments. The budget is checked "
        "between segments, never mid-segment, so a segment is never half-recorded.",
    )
    parser.add_argument(
        "--min-level",
        type=int,
        default=0,
        help="BA segmented only: skip segments below this level (2 = municipalities "
        "backbone only, skipping the unscoped catch-all and Bundesland probes; "
        "a canary dial)",
    )
    parser.add_argument(
        "--umkreis",
        type=int,
        default=0,
        help="BA segmented only: search radius in km. 0 (default) keeps Tier-3 "
        "provenance mapped; any radius downgrades Tier 3 to low_confidence.",
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
        help="NAV/TMT only: ignore the persisted poll cursor or watermark instead of "
        "resuming it. BA segmented: rebuild the frontier from the crosswalk instead "
        "of resuming pending segments.",
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
    max_segments: int | None = None,
    min_level: int = 0,
    umkreis: int = 0,
) -> BaseCollector:
    """Build the configured collector.

    ``since_days`` / ``max_details`` are NAV's feed-window and detail-budget
    dials, ``max_rows`` / ``only_status`` are Työmarkkinatori's stream dials,
    ``use_cursor`` is shared by both cursor-bearing sources, and
    ``max_segments`` / ``min_level`` / ``umkreis`` are BA segmented-mode dials;
    every other source's factory ignores them.
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
        max_segments=max_segments,
        min_level=min_level,
        umkreis=umkreis,
        fresh=not use_cursor,
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
    if args.segmented:
        # A segmented census runs in bounded resumable chunks; each chunk is a
        # separate invocation that walks the shared frontier. Stamp every chunk
        # with its run start so a resumed run writes a NEW partition instead of
        # overwriting the previous chunk's data — accumulation across chunks is
        # the consumer's job (the main app reads all partitions under the
        # scope; the push-readiness test dedupes on source_id).
        sweep_id = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    if args.panel:
        # One partition per panel sweep, stamped at run start so two sweeps on
        # the same day (or a re-run) never overwrite each other: the survival
        # series is built from the sequence of panel partitions.
        sweep_id = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = utc_iso(_dt.datetime.now(_dt.UTC))
    started_at = _dt.datetime.now(_dt.UTC)

    config = source_config(
        args.source, country=args.country, segmented=args.segmented, panel=args.panel
    )
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
        max_segments=args.max_segments,
        min_level=args.min_level,
        umkreis=args.umkreis,
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

    if isinstance(collector, BAJobsucheCollector):
        if collector.panel_regions:
            from collections import Counter

            statuses = Counter(r.region_mapping_status for r in rows)
            regions_with_rows = collector.panel_regions_with_rows
            advertised_total = sum(
                int(meta["advertised"] or 0) for meta in collector.panel_regions.values()
            )
            coverage += (
                f" Panel sweep: {collector.panel_regions_queried} frozen region "
                f"queries, {regions_with_rows} with >=1 row, "
                f"{collector.panel_regions_empty} with none; "
                f"{collector.panel_regions_capped} region(s) hit the declared page "
                f"cap (their stock is sampled, not enumerated); "
                f"{collector.panel_regions_short} region(s) paginated out before the "
                f"plan (stale advertised total); "
                f"{collector.panel_locality_mismatches} locality mismatch(es) against "
                f"the source's own woOutput echo; "
                f"{collector.panel_missing_envelope} page(s) without an ng-state "
                f"envelope. {collector.completed_pages} of {collector.total_pages} "
                f"planned pages fetched, {collector.failed_pages} non-200, "
                f"{collector.throttle_events} absorbed 403 throttle event(s) "
                f"(cooled down and retried, not failures). {collector.items_seen} items "
                f"parsed, {collector.duplicates_dropped} duplicate(s) dropped on HMAC "
                f"source_id; {len(rows)} rows written. Sum of the per-region advertised "
                f"totals (maxErgebnisse): {advertised_total} postings — the panel's "
                f"per-sweep regional denominator, recorded per region in "
                f"panel_regions.json; the rows are the capped sample of it. Region "
                f"mapping: mapped {statuses.get('mapped', 0)}, unmapped "
                f"{statuses.get('unmapped', 0)}, ambiguous {statuses.get('ambiguous', 0)}, "
                f"low_confidence {statuses.get('low_confidence', 0)}."
            )
        elif collector.frontier is not None:
            from collections import Counter

            methods = Counter(r.region_mapping_method for r in rows)
            statuses = Counter(r.region_mapping_status for r in rows)
            mapped = statuses.get("mapped", 0)
            total = len(rows)
            tier1 = methods.get("ba_city_municipality_nuts3", 0) + methods.get(
                "ba_city_qualifier_nuts3", 0
            )
            tier2 = methods.get("ba_segment_disambiguated", 0)
            tier3 = methods.get("ba_segment_provenance_nuts3", 0) + methods.get(
                "ba_segment_radius_nuts3", 0
            )
            pending = sum(
                1 for s in collector.frontier.segments.values() if s.status in ("pending", "failed")
            )
            coverage += (
                f" Segmented regional census: {collector.segments_processed} segment(s) "
                f"processed ({collector.segments_complete} complete, "
                f"{collector.segments_subdivided} subdivided, "
                f"{collector.segments_failed} failed); {pending} segment(s) still "
                f"pending in the frontier (data/state/ba_segment_frontier.json); "
                f"{collector.completed_pages} search pages fetched; "
                f"{collector.items_seen} items parsed, {collector.duplicates_dropped} "
                f"cross-segment duplicates dropped on HMAC source_id. Rows: {len(rows)} "
                f"this run ({collector.total_elements} distinct source_ids). Measured "
                f"German active-stock lower bound over complete segments: "
                f"{collector.measured_stock_lower_bound} postings. Region mapping: "
                f"mapped {mapped}/{total} ({100.0 * mapped / total:.1f}%), "
                f"unmapped {statuses.get('unmapped', 0)} ("
                f"{100.0 * statuses.get('unmapped', 0) / total:.1f}%), ambiguous "
                f"{statuses.get('ambiguous', 0)}, low_confidence "
                f"{statuses.get('low_confidence', 0)}; Tier 1 {tier1} / Tier 2 {tier2} / "
                f"Tier 3 {tier3} rows. Per-query cap: 400 pages x 25 = 10,000 listings; "
                f"every segment walked to completeness or provable truncation. Region "
                f"inference (Tiers 2/3) only resolves the region of real collected "
                f"postings; it never fabricates or scales rows. Non-geographic markers "
                f"classified ambiguous, never silently dropped."
            )
        else:
            coverage += (
                f" Sweep window: {collector.completed_pages} search pages fetched "
                f"({collector.total_pages} planned; {collector.empty_pages} empty after the "
                f"10,000-listing query window closed), {collector.failed_pages} non-200; "
                f"{collector.items_seen} items parsed, {collector.duplicates_dropped} "
                f"duplicates dropped on HMAC source_id. Rows collected: {len(rows)} of the "
                "10,000-listing per-query window the unscoped search advertises — a "
                "windowed sample of the active stock, not a complete snapshot."
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

    if isinstance(collector, BAJobsucheCollector) and collector.panel_regions:
        panel = build_panel(DEFAULT_REFERENCE)
        write_panel_regions(
            partition,
            {
                "scope_id": BA_PANEL_SCOPE_ID,
                "sweep_id": sweep_id,
                "observed_at": utc_iso(observed_at),
                "membership_hash": panel_membership_hash(panel),
                "frame_size": len(panel),
                "min_regions_required": BA_PANEL_MIN_REGIONS,
                "regions_queried": collector.panel_regions_queried,
                "regions_with_rows": collector.panel_regions_with_rows,
                "regions_empty": collector.panel_regions_empty,
                "regions_capped": collector.panel_regions_capped,
                "regions_short": collector.panel_regions_short,
                "locality_mismatches": collector.panel_locality_mismatches,
                "missing_envelope": collector.panel_missing_envelope,
                "failed_pages": collector.failed_pages,
                "throttle_events": collector.throttle_events,
                "duplicates_dropped": collector.duplicates_dropped,
                "regions": collector.panel_regions,
            },
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
