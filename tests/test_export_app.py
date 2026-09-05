"""Export-contract tests (Plan A v2, task A2): the app's numbers are the page's numbers.

The fresh app renders `app/data.json` and computes nothing, so the export is its
entire world. Two proofs live here: the numbers the export carries are the
numbers `publish.build_site` rendered from the same views (spot-checked on the
two-scope fixture, evidence dicts included), and the payload's schema is pinned
key by key so a silent field rename fails the build loudly.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
from pytest import MonkeyPatch

from scripts import export_app_data, publish

DE_LIMITATION = (
    "Stratified region-bounded sample with a capped within-stratum draw over a frozen panel"
)


def _two_scope_database(tmp_path: Path) -> Path:
    """Two collecting scopes over the publish-view shapes: a Swedish keyword scope
    with every insight rule's preconditions met (including a suppressed flow
    bucket), and a German panel scope whose occupation and skill fields are
    absent by construction."""
    database = tmp_path / "two-scope.duckdb"
    connection = duckdb.connect(str(database))
    connection.execute(
        """
        create table labour_demand_latest as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'SE'::varchar as country, timestamp '2026-08-06 09:00:00' as observed_at,
               40::bigint as active_postings, 'JobSearch current ads'::varchar as source_version,
               'https://data.jobtechdev.se/dataservice/jobsearch/'::varchar as licence_reference,
               'official-public-api'::varchar as access_method,
               'fresh'::varchar as freshness_status, 'covered'::varchar as coverage_status
        union all
        select 'ba', 'de-panel', 'DE', timestamp '2026-09-02 08:04:00', 20::bigint,
               'Jobsuche', cast(null as varchar), 'html-portal-scrape', 'fresh', 'covered'
        """
    )
    connection.execute(
        f"""
        create table source_coverage as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'sweep-one'::varchar as sweep_id, 'SE'::varchar as country,
               timestamp '2026-08-06 09:00:00' as observed_at, 40::bigint as expected_rows,
               40::bigint as observed_rows, 'fresh'::varchar as freshness_status,
               'covered'::varchar as coverage_status, 3.0::double as freshness_age_hours,
               'Keyword-scoped'::varchar as coverage_limitations,
               48::integer as freshness_threshold_hours
        union all
        select 'ba', 'de-panel', 'sweep-de', 'DE', timestamp '2026-09-02 08:04:00',
               20::bigint, 20::bigint, 'fresh', 'covered', 2.0::double,
               '{DE_LIMITATION}', 48
        """
    )
    connection.execute(
        """
        create table region_breadth_latest as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'SE'::varchar as country, 1::bigint as regions_with_postings,
               21::bigint as regions_in_frame
        union all
        select 'ba', 'de-panel', 'DE', 2::bigint, 4::bigint
        """
    )
    connection.execute(
        """
        create table dimension_demand_latest as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'sweep-one'::varchar as sweep_id, timestamp '2026-08-06 09:00:00' as observed_at,
               'region'::varchar as dimension, 'SE110'::varchar as value_uri,
               'Stockholms län'::varchar as value_label, 'NUTS-2024'::varchar as taxonomy_version,
               30::bigint as posting_count
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', timestamp '2026-08-06 09:00:00',
               'region', 'SE232', 'Västra Götalands län', 'NUTS-2024', 10::bigint
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', timestamp '2026-08-06 09:00:00',
               'occupation', 'http://data.europa.eu/esco/occupation/bd272aee',
               'Systemutvecklare/Programmerare', '1.2.1', 35::bigint
        union all
        select 'ba', 'de-panel', 'sweep-de', timestamp '2026-09-02 08:04:00', 'region',
               'DEB11', 'Koblenz, Kreisfreie Stadt', 'NUTS-2024', 12::bigint
        union all
        select 'ba', 'de-panel', 'sweep-de', timestamp '2026-09-02 08:04:00', 'region',
               'DE300', 'Berlin, Kreisfreie Stadt', 'NUTS-2024', 8::bigint
        """
    )
    connection.execute(
        """
        create table skill_demand_latest as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'sweep-one'::varchar as sweep_id, timestamp '2026-08-06 09:00:00' as observed_at,
               'skill'::varchar as dimension,
               'http://data.europa.eu/esco/skill/4c016b68'::varchar as value_uri,
               'Programmering'::varchar as value_label, '1.2.1'::varchar as taxonomy_version,
               8::bigint as posting_count
        """
    )
    connection.execute(
        """
        create table mapping_quality_latest as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'sweep-one'::varchar as sweep_id, 'region'::varchar as dimension,
               'mapped'::varchar as mapping_status, 'region_crosswalk'::varchar as mapping_method,
               cast(null as varchar) as mapping_confidence,
               'NUTS-2024'::varchar as taxonomy_version,
               40::bigint as outcome_count, 40::hugeint as total_outcomes
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', 'occupation', 'mapped',
               'esco_crosswalk', cast(null as varchar), '1.2.1', 35::bigint, 40::hugeint
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', 'occupation', 'not_present',
               'no_source_value', cast(null as varchar), '1.2.1', 5::bigint, 40::hugeint
        union all
        select 'ba', 'de-panel', 'sweep-de', 'region', 'mapped', 'ba_city_municipality_nuts3',
               cast(null as varchar), 'NUTS-2024', 20::bigint, 20::hugeint
        union all
        select 'ba', 'de-panel', 'sweep-de', 'occupation', 'not_present',
               'not_available_ba_html', cast(null as varchar), cast(null as varchar),
               20::bigint, 20::hugeint
        """
    )
    connection.execute(
        """
        create table mapping_coverage_latest as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'sweep-one'::varchar as sweep_id, 'region'::varchar as dimension,
               40::bigint as postings_total, 40::bigint as postings_with_source_value,
               40::bigint as postings_mapped, 'NUTS-2024'::varchar as taxonomy_version
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', 'occupation', 40::bigint, 40::bigint,
               35::bigint, '1.2.1'
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', 'skill', 40::bigint, 10::bigint,
               8::bigint, '1.2.1'
        union all
        select 'ba', 'de-panel', 'sweep-de', 'region', 20::bigint, 20::bigint, 20::bigint,
               'NUTS-2024'
        union all
        select 'ba', 'de-panel', 'sweep-de', 'occupation', 20::bigint, 0::bigint, 0::bigint,
               cast(null as varchar)
        union all
        select 'ba', 'de-panel', 'sweep-de', 'skill', 20::bigint, 0::bigint, 0::bigint,
               cast(null as varchar)
        """
    )
    connection.execute(
        """
        create table requirement_demand_latest as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'sweep-one'::varchar as sweep_id, timestamp '2026-08-06 09:00:00' as observed_at,
               'employment_type'::varchar as dimension, 'kpPX_CNN_gDU'::varchar as value_code,
               'Permanent employment (probationary period possible)'::varchar as value_label,
               'mapped'::varchar as mapping_status, 30::bigint as posting_count
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', timestamp '2026-08-06 09:00:00',
               'employment_type', 'sTu5_NBQ_udq', 'Fixed-term employment', 'mapped', 10::bigint
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', timestamp '2026-08-06 09:00:00',
               'working_hours_type', '6YE1_gAC_R2G', 'Full-time', 'mapped', 35::bigint
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', timestamp '2026-08-06 09:00:00',
               'working_hours_type', '947z_JGS_Uk2', 'Part-time', 'mapped', 5::bigint
        union all
        select 'ba', 'de-panel', 'sweep-de', timestamp '2026-09-02 08:04:00',
               'employment_type', 'kpPX_CNN_gDU',
               'Permanent employment (probationary period possible)', 'mapped', 12::bigint
        union all
        select 'ba', 'de-panel', 'sweep-de', timestamp '2026-09-02 08:04:00',
               'employment_type', 'sTu5_NBQ_udq', 'Fixed-term employment', 'mapped', 8::bigint
        union all
        select 'ba', 'de-panel', 'sweep-de', timestamp '2026-09-02 08:04:00',
               'working_hours_type', '6YE1_gAC_R2G', 'Full-time', 'mapped', 15::bigint
        union all
        select 'ba', 'de-panel', 'sweep-de', timestamp '2026-09-02 08:04:00',
               'working_hours_type', '947z_JGS_Uk2', 'Part-time', 'mapped', 5::bigint
        """
    )
    connection.execute(
        """
        create table posting_flows as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'day'::varchar as grain, timestamp '2026-08-04 00:00:00' as bucket_start,
               true as is_suppressed, cast(null as bigint) as openings,
               cast(null as bigint) as closures, cast(null as bigint) as active_postings,
               cast(null as bigint) as active_vacancies
        union all
        select 'jobtech', 'jobtech-scope', 'day', timestamp '2026-08-05 00:00:00', false,
               6::bigint, 0::bigint, 38::bigint, 50::bigint
        union all
        select 'jobtech', 'jobtech-scope', 'day', timestamp '2026-08-06 00:00:00', false,
               4::bigint, 2::bigint, 40::bigint, 52::bigint
        union all
        select 'jobtech', 'jobtech-scope', 'week', timestamp '2026-08-03 00:00:00', false,
               7::bigint, 1::bigint, 40::bigint, 52::bigint
        union all
        select 'ba', 'de-panel', 'week', timestamp '2026-09-01 00:00:00', false,
               9::bigint, 0::bigint, 20::bigint, 26::bigint
        """
    )
    connection.execute(
        """
        create table posting_survival as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'active'::varchar as lifecycle_status, false as is_suppressed,
               true as any_right_censored, 40::bigint as posting_count,
               52::bigint as advertised_vacancies, 0.0::double as median_duration_days,
               0.0::double as p25_duration_days, 1.0::double as p75_duration_days,
               1::bigint as max_duration_days
        union all
        select 'jobtech', 'jobtech-scope', 'inferred_absence', false, false, 6::bigint,
               8::bigint, 1.0::double, 0.0::double, 2.0::double, 5::bigint
        union all
        select 'ba', 'de-panel', 'active', false, true, 20::bigint, 26::bigint,
               0.0::double, 0.0::double, 1.0::double, 1::bigint
        """
    )
    connection.execute(
        f"""
        create table collection_frequency as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               3::bigint as complete_sweeps, timestamp '2026-08-04 09:00:00' as first_observed_at,
               timestamp '2026-08-06 09:00:00' as last_observed_at,
               36.0::double as median_interval_hours, 48::integer as freshness_threshold_hours,
               'Keyword-scoped'::varchar as coverage_limitations
        union all
        select 'ba', 'de-panel', 1::bigint, timestamp '2026-09-02 08:04:00',
               timestamp '2026-09-02 08:04:00', cast(null as double), 48,
               '{DE_LIMITATION}'
        """
    )
    connection.execute(
        """
        create table latest_complete_sweeps as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               timestamp '2026-08-06 09:00:00' as observed_at,
               'https://data.jobtechdev.se/dataservice/jobsearch/'::varchar as licence_reference,
               'official-public-api'::varchar as access_method,
               'JobSearch current ads'::varchar as source_version,
               'NUTS-2024'::varchar as nuts_version, 'v30'::varchar as jobtech_taxonomy_version,
               '1.2.1'::varchar as esco_version, 40::bigint as row_count
        union all
        select 'ba', 'de-panel', timestamp '2026-09-02 08:04:00', cast(null as varchar),
               'html-portal-scrape', 'Jobsuche', 'NUTS-2024', cast(null as varchar),
               cast(null as varchar), 20::bigint
        """
    )
    connection.close()
    return database


def _scope(payload: dict[str, Any], scope_id: str) -> dict[str, Any]:
    return next(scope for scope in payload["scopes"] if scope["scope_id"] == scope_id)


def test_export_numbers_equal_the_published_page(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Every figure the export carries is the figure build_site rendered: demand
    counts parsed back out of the page, region and requirement rows as exact cell
    fragments, flow buckets including the suppressed one, and every insight
    sentence with its evidence."""
    monkeypatch.delenv("OBSERVATIONS_PATH", raising=False)
    database = _two_scope_database(tmp_path)
    page_target = tmp_path / "index.html"
    assert publish.build_site(database, page_target) == 2
    page = page_target.read_text(encoding="utf-8")
    payload = export_app_data.build_payload(database, datetime(2026, 9, 5, 16, 0, tzinfo=UTC))
    assert [scope["scope_id"] for scope in payload["scopes"]] == ["jobtech-scope", "de-panel"]

    # Demand: the countries table's Postings cell for each scope's row equals the
    # export's active_postings, parsed back out of the rendered row.
    for scope in payload["scopes"]:
        row = re.search(
            rf"<td><strong>{scope['country']}</strong></td><td>{scope['source']}</td>"
            rf"<td>{re.escape(scope['scope_id'])}</td>.*?"
            r'<td class="count">([\d,]+)</td>',
            page,
            re.DOTALL,
        )
        assert row is not None, f"demand row for {scope['scope_id']} not rendered"
        assert int(row[1].replace(",", "")) == scope["demand"]["active_postings"]

    swedish = _scope(payload, "jobtech-scope")
    german = _scope(payload, "de-panel")

    # Region ranking: each exported row is the page's region-table row, verbatim.
    assert [(row["label"], row["postings"]) for row in swedish["regions_top"]] == [
        ("Stockholms län", 30),
        ("Västra Götalands län", 10),
    ]
    assert [(row["label"], row["postings"]) for row in german["regions_top"]] == [
        ("Koblenz, Kreisfreie Stadt", 12),
        ("Berlin, Kreisfreie Stadt", 8),
    ]
    for scope in payload["scopes"]:
        for row in scope["regions_top"]:
            assert (
                f"<td>{row['label']}</td><td>{row['taxonomy_version']}</td>"
                f'<td class="count">{row["postings"]:,}</td>' in page
            )

    # Requirements: each exported (code, count) pair is the page's row.
    for scope in payload["scopes"]:
        for entries in scope["requirements"].values():
            for row in entries:
                assert f'<td>{row["code"]}</td><td class="count">{row["count"]:,}</td>' in page, (
                    f"requirement row {row} not rendered"
                )

    # Flows: every bucket is the page's flow row; the suppressed bucket carries
    # nulls and the flag, and the page hatches it rather than printing a number.
    assert [row["bucket"] for row in swedish["flows_series"]["day"]] == [
        "2026-08-04",
        "2026-08-05",
        "2026-08-06",
    ]
    suppressed = swedish["flows_series"]["day"][0]
    assert suppressed["suppressed"] is True
    assert suppressed["openings"] is None and suppressed["closures"] is None
    assert suppressed["active"] is None
    assert (
        '<td>2026-08-04</td><td class="count suppressed">suppressed</td>'
        '<td class="count suppressed">suppressed</td>' in page
    )
    for grain, entries in swedish["flows_series"].items():
        for row in entries:
            if row["suppressed"]:
                continue
            assert (
                f"<td>jobtech-scope</td><td>{publish.GRAIN_LABELS[grain]}</td>"
                f'<td>{row["bucket"]}</td><td class="count">{row["openings"]:,}</td>'
                f'<td class="count">{row["closures"]:,}</td>'
                f'<td class="count">{row["active"]:,}</td>' in page
            )
    for row in german["flows_series"]["week"]:
        assert row["suppressed"] is False

    # Insights: every exported sentence appears on the page, in the page's
    # section order, and the evidence dicts are the fixture's own numbers.
    rules = {insight["rule"] for insight in swedish["insights"]}
    assert rules == {
        "latest_count",
        "most_requested_occupation",
        "most_requested_skill",
        "employment_shares",
        "working_hours_shares",
        "median_duration",
        "sweep_churn",
        "region_concentration",
    }
    assert {insight["rule"] for insight in german["insights"]} == {
        "latest_count",
        "employment_shares",
        "working_hours_shares",
        "region_concentration",
    }
    for scope in payload["scopes"]:
        for insight in scope["insights"]:
            assert insight["text"] in page, f"export-only sentence: {insight['text']}"
    by_rule = {insight["rule"]: insight for insight in swedish["insights"]}
    assert by_rule["latest_count"]["evidence"] == {
        "active_postings": 40,
        "observed_at": "2026-08-06",
    }
    assert by_rule["region_concentration"]["evidence"] == {
        "region_label": "Stockholms län",
        "leader_postings": 30,
        "mapped_postings": 40,
    }
    assert by_rule["sweep_churn"]["evidence"]["days_apart"] == 1
    assert by_rule["sweep_churn"]["evidence"]["openings"] == 4
    assert by_rule["median_duration"]["evidence"]["posting_count"] == 6

    # Denominators and mapping outcomes: the honesty laws' payload, including the
    # German occupation absence state.
    assert swedish["denominators"]["occupation"] == {
        "postings_total": 40,
        "postings_with_source_value": 40,
        "postings_mapped": 35,
    }
    assert german["denominators"]["occupation"] == {
        "postings_total": 20,
        "postings_with_source_value": 0,
        "postings_mapped": 0,
    }
    assert german["mappings"]["occupation"] == {"not_present": 20}
    assert swedish["breadth"] == {"regions_with_postings": 1, "regions_in_frame": 21}
    assert german["breadth"] == {"regions_with_postings": 2, "regions_in_frame": 4}
    assert german["coverage"]["coverage_limitations"] == DE_LIMITATION


def test_export_schema_shape_is_pinned(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """The contract, key by key: a silent field rename anywhere in the payload
    fails this test instead of reaching the app."""
    monkeypatch.delenv("OBSERVATIONS_PATH", raising=False)
    payload = export_app_data.build_payload(
        _two_scope_database(tmp_path), datetime(2026, 9, 5, 16, 0, tzinfo=UTC)
    )
    assert set(payload) == {"meta", "scopes"}
    assert set(payload["meta"]) == {"methodology_version", "built", "scope_count"}
    assert payload["meta"]["built"] == "2026-09-05T16:00:00+00:00"
    assert isinstance(payload["meta"]["methodology_version"], str)
    assert isinstance(payload["meta"]["scope_count"], int)
    for scope in payload["scopes"]:
        assert set(scope) == {
            "source",
            "scope_id",
            "country",
            "label",
            "demand",
            "coverage",
            "breadth",
            "frequency",
            "regions_top",
            "requirements",
            "mappings",
            "denominators",
            "flows_series",
            "insights",
        }
        assert set(scope["demand"]) == {
            "observed_at",
            "active_postings",
            "source_version",
            "licence_reference",
            "access_method",
            "freshness_status",
            "coverage_status",
        }
        assert set(scope["coverage"]) == {
            "observed_at",
            "expected_rows",
            "observed_rows",
            "freshness_status",
            "coverage_status",
            "freshness_age_hours",
            "coverage_limitations",
            "freshness_threshold_hours",
        }
        assert set(scope["breadth"]) == {"regions_with_postings", "regions_in_frame"}
        assert set(scope["frequency"]) == {
            "complete_sweeps",
            "first_observed_at",
            "last_observed_at",
            "median_interval_hours",
        }
        for row in scope["regions_top"]:
            assert set(row) == {"label", "postings", "taxonomy_version"}
        for entries in scope["requirements"].values():
            for row in entries:
                assert set(row) == {"label", "code", "count"}
        for entry in scope["denominators"].values():
            assert set(entry) == {
                "postings_total",
                "postings_with_source_value",
                "postings_mapped",
            }
        for dimension, statuses in scope["mappings"].items():
            assert dimension
            for status, count in statuses.items():
                assert status and isinstance(count, int)
        for entries in scope["flows_series"].values():
            for row in entries:
                assert set(row) == {"bucket", "openings", "closures", "active", "suppressed"}
                assert isinstance(row["suppressed"], bool)
                assert isinstance(row["bucket"], str)
        for row in scope["insights"]:
            assert set(row) == {"rule", "text", "evidence"}
            assert row["rule"], "every exported sentence must name its rule"
            assert row["evidence"]


def test_export_app_data_writes_the_stamped_file(tmp_path: Path) -> None:
    """export_data writes app/data.json with the methodology version stamped."""
    database = _two_scope_database(tmp_path)
    target = tmp_path / "app" / "data.json"
    assert export_app_data.export_data(database, target) == 2
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["meta"]["methodology_version"] == publish.METHODOLOGY_VERSION
    assert payload["meta"]["scope_count"] == 2
    datetime.fromisoformat(payload["meta"]["built"])
