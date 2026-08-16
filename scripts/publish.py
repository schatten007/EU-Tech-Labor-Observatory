"""Build the offline labour-demand page from transformed aggregates."""

# ruff: noqa: E501 - keeping the self-contained HTML/CSS readable is the smaller option.

from __future__ import annotations

import os
from datetime import datetime
from html import escape
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / os.environ.get("DUCKDB_PATH", "data/dev.duckdb")
TARGET = ROOT / "site" / "build" / "index.html"

# Mirrors small_count_threshold() in transform/macros/suppress_small_counts.sql.
SUPPRESSION_THRESHOLD = 5
GRAIN_LABELS = {"day": "Daily", "week": "Weekly", "month": "Monthly"}
LIFECYCLE_LABELS = {
    "active": "Active (open at last sweep)",
    "source_reported": "Source-reported removal",
    "inferred_absence": "Inferred removal",
}


def _count(value: int | None) -> str:
    """Render a possibly suppressed small-count cell."""
    return f"{value:,}" if value is not None else "suppressed"


def _stat(value: float | None) -> str:
    """Render an optional duration statistic; a dash reads better than 'suppressed' here."""
    return f"{value:.1f}" if value is not None else "—"


def build_site(database: Path, target: Path) -> int:
    connection = duckdb.connect(str(database), read_only=True)
    rows: list[tuple[str, str | None, datetime, int, str, str, str, str, str]] = connection.execute(
        """
            select
                source,
                country,
                observed_at,
                active_postings,
                source_version,
                licence_reference,
                access_method,
                freshness_status,
                coverage_status
            from labour_demand_latest
            order by active_postings desc, source, country
            """
    ).fetchall()
    dimension_rows: list[tuple[str, str, int]] = connection.execute(
        """
        select dimension, value_label, posting_count
        from (
            select dimension, value_label, posting_count from dimension_demand_latest
            union all
            select dimension, value_label, posting_count from skill_demand_latest
        )
        order by posting_count desc, dimension, value_label
        limit 20
        """
    ).fetchall()
    quality_rows: list[tuple[str, str, int]] = connection.execute(
        "select dimension, mapping_status, sum(outcome_count)::bigint "
        "from mapping_quality_latest group by all order by dimension, mapping_status"
    ).fetchall()
    flow_rows: list[tuple[str, str, datetime, int | None, int | None, int | None, int | None]] = (
        connection.execute(
            """
            select scope_id, grain, bucket_start, openings, closures, active_postings, active_vacancies
            from posting_flows
            order by scope_id, case grain when 'day' then 1 when 'week' then 2 else 3 end, bucket_start
            """
        ).fetchall()
    )
    survival_rows: list[
        tuple[
            str,
            str,
            bool,
            int | None,
            int | None,
            float | None,
            float | None,
            float | None,
            int | None,
        ]
    ] = connection.execute(
        """
        select scope_id, lifecycle_status, any_right_censored, posting_count, advertised_vacancies,
               median_duration_days, p25_duration_days, p75_duration_days, max_duration_days
        from posting_survival
        order by scope_id, case lifecycle_status when 'active' then 1 when 'source_reported' then 2 else 3 end
        """
    ).fetchall()
    frequency_rows: list[
        tuple[str, int, datetime, datetime, float | None, int | None, str | None]
    ] = connection.execute(
        """
            select scope_id, complete_sweeps, first_observed_at, last_observed_at,
                   median_interval_hours, freshness_threshold_hours, coverage_limitations
            from collection_frequency
            order by scope_id
            """
    ).fetchall()
    connection.close()
    maximum = max((row[3] for row in rows), default=0) or 1
    table_rows = "".join(
        f"""
        <tr>
          <td><strong>{escape(country or "No postings")}</strong></td>
          <td>{escape(source)}</td>
          <td>{escape(source_version)}</td>
          <td><time datetime="{observed_at.isoformat()}">{observed_at:%Y-%m-%d %H:%M} UTC</time></td>
          <td>{escape(freshness_status)}</td>
          <td>{escape(coverage_status)}</td>
          <td class="count">{count:,}</td>
          <td class="bar-cell"><span class="bar" style="width:{100 * count / maximum:.1f}%"></span></td>
          <td><a href="{escape(licence_reference, quote=True)}">Licence</a><br><small>{escape(access_method)}</small></td>
        </tr>"""
        for (
            source,
            country,
            observed_at,
            count,
            source_version,
            licence_reference,
            access_method,
            freshness_status,
            coverage_status,
        ) in rows
    )
    dimension_table = "".join(
        f"<tr><td>{escape(dimension)}</td><td>{escape(label)}</td><td>{count:,}</td></tr>"
        for dimension, label, count in dimension_rows
    )
    quality_table = "".join(
        f"<tr><td>{escape(dimension)}</td><td>{escape(status)}</td><td>{count:,}</td></tr>"
        for dimension, status, count in quality_rows
    )
    flows_table = "".join(
        f"<tr><td>{escape(scope_id)}</td><td>{GRAIN_LABELS.get(grain, grain)}</td>"
        f'<td>{bucket_start:%Y-%m-%d}</td><td class="count">{_count(openings)}</td>'
        f'<td class="count">{_count(closures)}</td><td class="count">{_count(active_postings)}</td>'
        f'<td class="count">{_count(active_vacancies)}</td></tr>'
        for scope_id, grain, bucket_start, openings, closures, active_postings, active_vacancies in flow_rows
    )
    survival_table = "".join(
        f"<tr><td>{escape(LIFECYCLE_LABELS.get(status, status))}"
        f"{' <small>(censored)</small>' if censored else ''}</td>"
        f'<td class="count">{_count(postings)}</td><td class="count">{_count(vacancies)}</td>'
        f'<td class="count">{_stat(median)}</td>'
        f'<td class="count">{"—" if p25 is None and p75 is None else f"{_stat(p25)}–{_stat(p75)}"}</td>'
        f'<td class="count">{_stat(max_days)}</td></tr>'
        for scope_id, status, censored, postings, vacancies, median, p25, p75, max_days in survival_rows
    )
    frequency_table = "".join(
        f'<tr><td>{escape(scope_id)}</td><td class="count">{sweeps:,}</td>'
        f"<td>{first:%Y-%m-%d} to {last:%Y-%m-%d}</td>"
        f'<td class="count">{_stat(interval)}</td>'
        f'<td class="count">{threshold if threshold is not None else "—"}</td>'
        f"<td>{escape(limitations or '')}</td></tr>"
        for scope_id, sweeps, first, last, interval, threshold, limitations in frequency_rows
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>EU Tech Labour Observatory</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; color: #17201c; background: #f4f6f5; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; }}
    header {{ background: #163d2c; color: white; border-bottom: 5px solid #efb744; }}
    header div, main {{ width: min(1080px, calc(100% - 32px)); margin: auto; }}
    header div {{ padding: 24px 0 20px; }}
    h1 {{ margin: 0; font-size: 2.2rem; letter-spacing: 0; }}
    header p {{ margin: 6px 0 0; color: #dce9e2; }}
    main {{ padding: 28px 0 48px; }}
    .summary {{ margin-bottom: 22px; }}
    .label, caption {{ color: #53605a; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid #cbd3cf; background: white; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 720px; }}
    caption {{ text-align: left; padding: 14px 16px; font-size: .9rem; }}
    th, td {{ padding: 13px 16px; border-top: 1px solid #e1e6e3; text-align: left; white-space: nowrap; }}
    th {{ font-size: .78rem; text-transform: uppercase; color: #53605a; background: #f8faf9; }}
    .count {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .bar-cell {{ width: 18%; }}
    .bar {{ display: block; height: 10px; background: #27845b; min-width: 2px; }}
    a {{ color: #155f43; }}
    small {{ color: #65716b; }}
    footer {{ margin-top: 18px; color: #65716b; font-size: .85rem; }}
    @media (max-width: 600px) {{ h1 {{ font-size: 1.45rem; }} .summary {{ display: block; }} header div, main {{ width: min(100% - 24px, 1080px); }} }}
  </style>
</head>
<body>
  <header><div>
    <h1>EU Tech Labour Observatory</h1>
    <p>Latest observed public technology job postings</p>
  </div></header>
  <main>
    <section class="summary" aria-label="Summary">
      <span class="label">{len(rows)} independently sourced country observation(s). Counts are not summed or deduplicated across sources.</span>
    </section>
    <div class="table-wrap">
      <table>
        <caption>Counts reflect the latest complete approved sweep for each source and scope, not estimated vacancies.</caption>
        <thead><tr><th>Country</th><th>Source</th><th>Version</th><th>Observed</th><th>Freshness</th><th>Coverage</th><th class="count">Postings</th><th>Relative volume</th><th>Access</th></tr></thead>
        <tbody>{table_rows}</tbody>
      </table>
     </div>
    <section class="tables" aria-label="Mapped demand">
      <p class="label">Mappings use pinned reference data: NUTS 2024 regions, JobTech Taxonomy v30, and ESCO 1.2.1. Only structured taxonomy fields are used; job titles and free text are never classified. Sweden only: no German posting source has passed the approval gate. Ambiguous, low-confidence, unmapped, and not-present values are excluded from mapped demand and shown separately as mapping quality.</p>
      <div class="table-wrap"><table><caption>Latest mapped demand by region, occupation, and skill</caption>
        <thead><tr><th>Dimension</th><th>Value</th><th class="count">Postings</th></tr></thead>
        <tbody>{dimension_table or '<tr><td colspan="3">No mapped dimension results</td></tr>'}</tbody>
      </table></div>
      <div class="table-wrap"><table><caption>Mapping quality outcomes</caption>
        <thead><tr><th>Dimension</th><th>Status</th><th class="count">Outcomes</th></tr></thead>
        <tbody>{quality_table or '<tr><td colspan="3">No mapping quality results</td></tr>'}</tbody>
      </table></div>
    </section>
    <section class="tables" aria-label="Historical analytics">
      <p class="label">Historical view. A posting leaving the source is reported as posting duration or inferred removal, never as time to hire. Trends are read within a single source and scope; counts are not summed across sources or compared as absolute values between countries. Active-posting durations are right-censored lower bounds, not completed survival. Cells covering fewer than {SUPPRESSION_THRESHOLD} postings are suppressed to avoid singling out an individual posting.</p>
      <div class="table-wrap"><table><caption>Posting openings, active stock, and closures over time (daily, weekly, monthly)</caption>
        <thead><tr><th>Scope</th><th>Period</th><th>Bucket</th><th class="count">Openings</th><th class="count">Closures</th><th class="count">Active postings</th><th class="count">Active vacancies</th></tr></thead>
        <tbody>{flows_table or '<tr><td colspan="7">No trend results</td></tr>'}</tbody>
      </table></div>
      <div class="table-wrap"><table><caption>Posting survival by closure basis. Advertised vacancies are counted separately from postings.</caption>
        <thead><tr><th>Basis</th><th class="count">Postings</th><th class="count">Advertised vacancies</th><th class="count">Median days</th><th class="count">P25–P75 days</th><th class="count">Max days</th></tr></thead>
        <tbody>{survival_table or '<tr><td colspan="6">No survival results</td></tr>'}</tbody>
      </table></div>
      <div class="table-wrap"><table><caption>Source coverage and collection frequency, published beside the metrics.</caption>
        <thead><tr><th>Scope</th><th class="count">Complete sweeps</th><th>Observed span</th><th class="count">Median interval (h)</th><th class="count">Freshness threshold (h)</th><th>Known comparability limitations</th></tr></thead>
        <tbody>{frequency_table or '<tr><td colspan="6">No coverage results</td></tr>'}</tbody>
      </table></div>
    </section>
    <footer>Aggregate observations only. Native posting identifiers and private text are not published.</footer>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    return len(rows)


def main() -> int:
    count = build_site(DATABASE, TARGET)
    print(f"wrote {TARGET.relative_to(ROOT)} ({count} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
