"""Offline JSON export for the fresh presentation app (Plan A v2, task A2).

The app never computes a statistic: if a number is not in this export, it is not
shown. The export reads exactly what ``publish.build_site`` reads - the same
DuckDB publish views through the same query functions - and runs the same
``insights.build`` rules with their evidence dicts, so the app's numbers and the
audit page's numbers cannot drift apart. The honesty laws survive the rendering
layer because the export itself carries the methodology version, the
denominators beside every ranking, the suppression flags on every flow bucket,
and the absence states (null frames, zero-source-value dimensions).

stdlib + duckdb only. The schema is pinned by tests/test_export_app.py: a silent
field rename fails the build loudly.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from scripts import insights, publish

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / os.environ.get("DUCKDB_PATH", "data/dev.duckdb")
TARGET = ROOT / "app" / "data.json"


def build_payload(database: Path, built: datetime) -> dict[str, Any]:
    """Read the publish views once and assemble the app's entire world.

    ``built`` is injected so tests get a deterministic meta block; the live run
    stamps the current UTC time exactly as ``publish.build_site`` does.
    """
    connection = duckdb.connect(str(database), read_only=True)
    try:
        demand = publish._query_demand(connection)
        coverage = publish._query_coverage(connection)
        region_breadth = publish._query_region_breadth(connection)
        regions = publish._query_dimension(connection, region=True)
        occupations = publish._query_dimension(connection, region=False)
        skills = publish._query_skills(connection)
        mapping = publish._query_mapping(connection)
        mapping_coverage = publish._query_mapping_coverage(connection)
        requirements = publish._query_requirements(connection)
        flows = publish._query_flows(connection)
        survival = publish._query_survival(connection)
        frequency = publish._query_frequency(connection)
    finally:
        connection.close()
    # Same call, same argument order as build_site: the exported sentences are
    # the page's sentences, evidence dicts included.
    insights_by_section = insights.build(
        demand,
        coverage,
        occupations,
        skills,
        mapping_coverage,
        requirements,
        survival,
        flows,
        frequency,
        regions,
    )
    # The scope-keyed views carry no country column; build_site builds this
    # crosswalk for its filter bar, and the export needs the same country chips.
    countries: dict[str, str | None] = {row[1]: row[2] for row in demand if row[2]}
    countries.update({row[1]: row[2] for row in coverage if row[2]})
    scopes: list[dict[str, Any]] = []
    for row in demand:
        source, scope_id = row[0], row[1]
        if any(scope["source"] == source and scope["scope_id"] == scope_id for scope in scopes):
            continue
        scopes.append(
            _scope_payload(
                source,
                scope_id,
                countries.get(scope_id),
                demand,
                coverage,
                region_breadth,
                regions,
                mapping,
                mapping_coverage,
                requirements,
                flows,
                frequency,
                insights_by_section,
            )
        )
    return {
        "meta": {
            "methodology_version": publish.METHODOLOGY_VERSION,
            "built": built.isoformat(),
            "scope_count": len(scopes),
        },
        "scopes": scopes,
    }


def _scope_payload(
    source: str,
    scope_id: str,
    country: str | None,
    demand: list[publish.DemandRow],
    coverage: list[publish.CoverageRow],
    region_breadth: list[publish.RegionBreadthRow],
    regions: list[publish.ScopedDimensionRow],
    mapping: list[publish.ScopedMappingRow],
    mapping_coverage: list[publish.MappingCoverageRow],
    requirements: list[publish.ScopedRequirementRow],
    flows: list[publish.FlowRow],
    frequency: list[publish.FrequencyRow],
    insights_by_section: dict[str, list[insights.Insight]],
) -> dict[str, Any]:
    """One scope's block: every figure keyed to this (source, scope_id) alone.

    Nothing here sums or compares across scopes; flows, survival and frequency
    are scope-keyed views, matched the same way the page and the insight rules
    match them, by scope_id.
    """
    demand_row = next((row for row in demand if row[0] == source and row[1] == scope_id), None)
    coverage_row = next((row for row in coverage if row[0] == source and row[1] == scope_id), None)
    breadth_row = next(
        (row for row in region_breadth if row[0] == source and row[1] == scope_id), None
    )
    frequency_row = next((row for row in frequency if row[0] == scope_id), None)
    scope_flows = [row for row in flows if row[0] == scope_id]
    flows_series: dict[str, list[dict[str, Any]]] = {}
    for (
        _scope,
        grain,
        bucket_start,
        openings,
        closures,
        active,
        _vacancies,
        _flow_source,
    ) in scope_flows:
        flows_series.setdefault(grain, []).append(
            {
                "bucket": bucket_start.strftime("%Y-%m-%d"),
                "openings": openings,
                "closures": closures,
                "active": active,
                # The view suppresses each small count independently, so a null
                # measure is the suppression signal the page renders as hatched
                # cells; the flag says the bucket must never chart as zero.
                "suppressed": any(value is None for value in (openings, closures, active)),
            }
        )
    scope_requirements: dict[str, list[dict[str, Any]]] = {}
    for row in requirements:
        if row[0] == source and row[1] == scope_id:
            scope_requirements.setdefault(row[2], []).append(
                {"label": row[3], "code": row[4], "count": row[6]}
            )
    scope_mappings: dict[str, dict[str, int]] = {}
    for outcome in mapping:
        if outcome[0] == source and outcome[1] == scope_id:
            scope_mappings.setdefault(outcome[2], {})[outcome[3]] = outcome[4]
    # The denominator for every ranking: a dimension whose source-value count is
    # zero is absent by construction, and the app must state that, not chart it.
    denominators: dict[str, dict[str, int]] = {
        row[2]: {
            "postings_total": row[3],
            "postings_with_source_value": row[4],
            "postings_mapped": row[5],
        }
        for row in mapping_coverage
        if row[0] == source and row[1] == scope_id
    }
    # The page renders insight sentences in SECTIONS order; the export keeps the
    # same order so the app's fact lines read like the board's.
    scope_insights = [
        {
            "rule": insight.rule,
            "text": insight.text,
            "evidence": insight.evidence,
        }
        for slug, _heading in publish.SECTIONS
        for insight in insights_by_section.get(slug, [])
        if insight.scope == scope_id
    ]
    return {
        "source": source,
        "scope_id": scope_id,
        "country": country,
        "label": publish._scope_label(source, scope_id),
        "demand": {
            "observed_at": demand_row[3].isoformat() if demand_row else None,
            "active_postings": demand_row[4] if demand_row else None,
            "source_version": demand_row[5] if demand_row else None,
            "licence_reference": demand_row[6] if demand_row else None,
            "access_method": demand_row[7] if demand_row else None,
            "freshness_status": demand_row[8] if demand_row else None,
            "coverage_status": demand_row[9] if demand_row else None,
        },
        "coverage": {
            "observed_at": coverage_row[3].isoformat() if coverage_row else None,
            "expected_rows": coverage_row[4] if coverage_row else None,
            "observed_rows": coverage_row[5] if coverage_row else None,
            "freshness_status": coverage_row[6] if coverage_row else None,
            "coverage_status": coverage_row[7] if coverage_row else None,
            "freshness_age_hours": coverage_row[8] if coverage_row else None,
            "coverage_limitations": coverage_row[9] if coverage_row else None,
            "freshness_threshold_hours": coverage_row[10] if coverage_row else None,
        },
        "breadth": {
            "regions_with_postings": breadth_row[3] if breadth_row else None,
            "regions_in_frame": breadth_row[4] if breadth_row else None,
        },
        "frequency": {
            "complete_sweeps": frequency_row[1] if frequency_row else None,
            "first_observed_at": frequency_row[2].isoformat() if frequency_row else None,
            "last_observed_at": frequency_row[3].isoformat() if frequency_row else None,
            "median_interval_hours": frequency_row[4] if frequency_row else None,
        },
        # Already truncated at DIMENSION_LIMIT by the query, exactly as the page
        # renders it; the unlisted tail is the denominator's job to state.
        "regions_top": [
            {"label": row[3], "postings": row[5], "taxonomy_version": row[4]}
            for row in regions
            if row[0] == source and row[1] == scope_id
        ],
        "requirements": scope_requirements,
        "mappings": scope_mappings,
        "denominators": denominators,
        "flows_series": flows_series,
        "insights": scope_insights,
    }


def export_data(database: Path, target: Path) -> int:
    payload = build_payload(database, datetime.now(UTC))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return int(payload["meta"]["scope_count"])


def main() -> int:
    count = export_data(DATABASE, TARGET)
    print(f"wrote {TARGET.relative_to(ROOT)} ({count} scopes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
