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


def build_site(database: Path, target: Path) -> int:
    rows: list[tuple[str, str | None, datetime, int]] = (
        duckdb.connect(str(database), read_only=True)
        .execute(
            """
            select source, country, observed_at, active_postings
            from labour_demand_latest
            order by active_postings desc, source, country
            """
        )
        .fetchall()
    )
    total = sum(row[3] for row in rows)
    maximum = max((row[3] for row in rows), default=0) or 1
    table_rows = "".join(
        f"""
        <tr>
          <td><strong>{escape(country or "No postings")}</strong></td>
          <td>{escape(source)}</td>
          <td><time datetime="{observed_at.isoformat()}">{observed_at:%Y-%m-%d %H:%M} UTC</time></td>
          <td class="count">{count:,}</td>
          <td class="bar-cell"><span class="bar" style="width:{100 * count / maximum:.1f}%"></span></td>
        </tr>"""
        for source, country, observed_at, count in rows
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
    .summary {{ display: flex; gap: 28px; align-items: baseline; margin-bottom: 22px; }}
    .total {{ font-size: 2.4rem; font-weight: 750; }}
    .label, caption {{ color: #53605a; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid #cbd3cf; background: white; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 720px; }}
    caption {{ text-align: left; padding: 14px 16px; font-size: .9rem; }}
    th, td {{ padding: 13px 16px; border-top: 1px solid #e1e6e3; text-align: left; white-space: nowrap; }}
    th {{ font-size: .78rem; text-transform: uppercase; color: #53605a; background: #f8faf9; }}
    .count {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .bar-cell {{ width: 28%; }}
    .bar {{ display: block; height: 10px; background: #27845b; min-width: 2px; }}
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
      <span class="total">{total:,}</span><span class="label">active postings across {len(rows)} source-country observations</span>
    </section>
    <div class="table-wrap">
      <table>
        <caption>Counts reflect the latest complete sweep for each source, not estimated vacancies.</caption>
        <thead><tr><th>Country</th><th>Source</th><th>Observed</th><th class="count">Postings</th><th>Relative volume</th></tr></thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>
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
