"""Build the offline labour-demand dashboard from transformed aggregates."""

# ruff: noqa: E501 - keeping the self-contained HTML/CSS/JS readable is the smaller option.

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path

import duckdb

from scripts import insights

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / os.environ.get("DUCKDB_PATH", "data/dev.duckdb")
TARGET = ROOT / "site" / "build" / "index.html"

# Mirrors small_count_threshold() in transform/macros/suppress_small_counts.sql.
# ponytail: one Python definition, reused everywhere; do not add a second literal.
SUPPRESSION_THRESHOLD = 5
DIMENSION_LIMIT = 25
GRAIN_LABELS = {"day": "Daily", "week": "Weekly", "month": "Monthly"}
GRAIN_RANK = {"day": 1, "week": 2, "month": 3}
LIFECYCLE_LABELS = {
    "active": "Active (open at last sweep)",
    "source_reported": "Source-reported removal",
    "inferred_absence": "Inferred removal",
}
FRESHNESS_LABELS = {"fresh": "Fresh", "stale": "Stale data", "unknown": "Unknown freshness"}
COVERAGE_LABELS = {
    "covered": "Covered",
    "invalid": "Partial coverage",
    "unknown_metadata": "Unknown coverage",
}
SECTIONS = (
    ("overview", "Overview"),
    ("status", "Status"),
    ("countries", "Countries"),
    ("occupations", "Occupations and skills"),
    ("requirements", "Requirements"),
    ("survival", "Survival"),
    ("quality", "Data quality"),
    ("methodology", "Methodology"),
    ("governance", "Governance"),
)
# The three requirement dimensions, in the order they are published: slug, heading, and the noun
# used in the caption. Mirrors REQUIREMENT_DIMENSIONS in scripts/enrich.py.
REQUIREMENT_SECTIONS = (
    ("employment_type", "Employment type", "employment type"),
    ("working_hours_type", "Working hours", "working-hours type"),
    ("duration", "Contract duration", "contract duration"),
)
WORKFLOW = (
    "Select a country or NUTS region and technology occupation.",
    "Inspect current posting demand and source coverage.",
    "Compare frequently observed and changing skills.",
    "Review historical trends and posting duration as supporting context.",
)

# ponytail: one hand-bumped version per published definition set, stamped on the page and on
# every CSV download so a saved file can be traced back to the definitions that produced it.
# 1.1: a sole exact match now resolves a multi-candidate crosswalk concept, so figures published
# under 1.0 came from a stricter mapping rule and the two are not one series.
# 1.2: three requirement dimensions are published from a new reference file, mapped by rules this
# version claims to cover. 13a's lesson was exactly this: a mapping change under a stale version
# breaks the traceability the version exists to provide.
# 1.3: this page publishes derived statements (scripts/insights.py) that are definitions in the
# only sense that matters - a median, a share, a superlative, each with its own rule for when it
# appears and which denominator it carries. 1.2 published no such sentence at all, so the bump is a
# fact about the page, decided before the first insight rendered.
# 1.4: the page now states its own sampling designs and an occupation gap. The `ba/de-nuts3-panel`
# scope is a stratified region-bounded sample with a capped within-stratum draw over a frozen
# NUTS-3 panel - not a census and not a partial crawl - and the Swedish keyword scope is a
# keyword-scoped query, not a sample. One published scope carries no structured occupation
# field, which is why one occupation ranking is empty by construction. Region breadth - the
# count of NUTS-3 regions with at least one mapped posting against the pinned frame
# (Increment 22) - is a new published figure of the same kind: a rule deciding whether and
# against which denominator a number is stated.
# 1.5: two derived statements joined the page, both computed per scope from rows the page
# already publishes: regional concentration (the leading region's share of mapped postings,
# stated as counts) and sweep-over-sweep churn (openings and closures between the two most
# recent daily buckets, with the bucket spacing stated). Both are definitions in the same
# sense as 1.3's sentences - rules deciding when a number is stated - so they cannot share a
# version with pages that lack them.
METHODOLOGY_VERSION = "1.5"
# Mirrors the offline default in transform/models/staging/stg_postings.sql.
SAMPLE_OBSERVATIONS = "data/sample/postings_sample.ndjson"
SOURCE_TERMS = {
    "jobtech": (
        "Attribute Arbetsförmedlingen / JobTech Development. Aggregates may be republished; "
        "posting text and identifiers may not.",
        "Pseudonymised observations stay in private append-only partitions and are never published.",
    )
}
DEFAULT_TERMS = (
    "Reuse terms are recorded per sweep in the licence reference beside this row.",
    "Pseudonymised observations stay in private append-only partitions and are never published.",
)
RETENTION = (
    (
        "Raw collection partitions",
        "Kept indefinitely and never rewritten. History is append-only, so a posting that "
        "disappears becomes an event rather than a deletion. These partitions stay private.",
    ),
    (
        "Published aggregates",
        "Rebuilt from the views on every publication. This page holds no per-posting row, so "
        "there is nothing on it to delete or amend for an individual posting.",
    ),
    (
        "Pseudonymisation keys",
        "Held outside the repository and versioned. Retired key versions are retained so that a "
        "key rotation is never read as a wave of posting removals.",
    ),
    (
        "Reference crosswalks",
        "Pinned snapshots are kept, and the version used is printed beside every mapped figure.",
    ),
)
PRIVACY = (
    "Job postings are employer adverts, but their free text can carry personal data, so free text "
    "never leaves the collector: scripts/sanitize.py applies an explicit field allowlist and drops "
    "everything outside it.",
    "The native posting identifier is replaced by an HMAC pseudonym under a versioned secret. The "
    "secret is not published, so a pseudonym cannot be resolved back to a source record from here.",
    "Only aggregates are published. Native identifiers, source URLs, employer names, and posting "
    "text are absent by construction rather than removed after the fact.",
    "Residual risk, stated plainly: latest-sweep counts by country, region, occupation, skill, and "
    "the three requirement dimensions are published in full, so a rare combination can be a small "
    "number. Those cells count postings, carry no employer, no geography finer than a NUTS region, "
    "and no text, and each table is a single-dimension distribution rather than a cross-tabulation, "
    "so no combination of two dimensions is available to a reader and a small count cannot single "
    "out a person.",
)
ARCHITECTURE = (
    (
        "1. Collect",
        "scripts/collect.py reads one complete sweep from a documented public API, page by page, "
        "and stores it as an append-only partition beside a manifest of expected and observed rows.",
    ),
    (
        "2. Enrich",
        "scripts/enrich.py maps structured geography, occupation, skill, and requirement fields "
        "onto pinned NUTS, JobTech Taxonomy, and ESCO reference data. Free text is never classified.",
    ),
    (
        "3. Sanitize",
        "scripts/sanitize.py is the privacy boundary: it pseudonymises the native identifier and "
        "keeps only allowlisted fields before anything is stored for analysis.",
    ),
    (
        "4. Transform",
        "dbt builds views only: staging, a derived posting event log, and the publish views, each "
        "under an enforced column contract with data tests.",
    ),
    (
        "5. Publish",
        "scripts/publish.py queries the publish views and writes this single self-contained page. "
        "No external assets, no analytics, and no network access at page-build time.",
    ),
)

DemandRow = tuple[str, str, str | None, datetime, int, str, str, str, str, str]
# ponytail: freshness_threshold_hours is appended last so the existing index maths stays put;
# it must come from the same sweep that produced freshness_status, not from a history aggregate.
CoverageRow = tuple[
    str, str, str | None, datetime, int, int, str, str, float | None, str | None, int | None
]
DimensionRow = tuple[str, str, str, int]
# (dimension, value_label, value_code, mapping_status, posting_count): the code is nullable because
# a `Not stated` row is a posting whose source field was empty and so has no code to publish.
RequirementRow = tuple[str, str, str | None, str, int]
MappingRow = tuple[str, str, int]
# The scope-keyed query results: (source, scope_id) prefixed onto the published row so the
# publisher can group per scope and insights can partition before any rule runs. The published
# row shapes above stay unchanged, so the renderers' index maths stays put.
ScopeKey = tuple[str, str]
ScopedDimensionRow = tuple[str, str, str, str, str, int]
ScopedMappingRow = tuple[str, str, str, str, int]
ScopedRequirementRow = tuple[str, str, str, str, str | None, str, int]
# (source, scope_id, dimension, postings_total, postings_with_source_value, postings_mapped):
# the scope keys are carried so the single-scope guard and the denominators read the same rows.
MappingCoverageRow = tuple[str, str, str, int, int, int]
# (source, scope_id, country, regions_with_postings, regions_in_frame): one row per scope from
# region_breadth_latest. regions_in_frame is null when no NUTS-3 reference frame is pinned for
# the scope's country, which renders as the degraded no-frame sentence, not as a wrong number.
RegionBreadthRow = tuple[str, str, str | None, int, int | None]
# ponytail: the scope-keyed rows carry `source` last so the existing index maths and helpers
# stay put; only the filter attributes read it.
FlowRow = tuple[str, str, datetime, int | None, int | None, int | None, int | None, str]
SurvivalRow = tuple[
    str,
    str,
    bool,
    int | None,
    int | None,
    float | None,
    float | None,
    float | None,
    int | None,
    str,
]
FrequencyRow = tuple[str, int, datetime, datetime, float | None, int | None, str | None, str]
ProvenanceRow = tuple[
    str, str, datetime, str | None, str | None, str | None, str | None, str | None, str | None, int
]

# Palette and type system per design/UI_REDESIGN_SPEC.md (§1.2, §1.3), guideline-reviewed
# 2026-09-04: contrast computed in §5.1; bright amber never fills a lamp and never outlines
# focus alone; no white text on Signal Green.
STYLE = r"""
    :root {
      color-scheme: light;
      /* core palette (spec §1.2) */
      --housing: #163d2c;
      --signal: #27845b;
      --caution: #efb744;
      --ink: #17201c;
      --ink-soft: #4c5b54;
      --ground: #f4f6f5;
      --panel: #ffffff;
      /* lines and states */
      --line: #cbd3cf;
      --line-soft: #e1e6e3;
      --brand-ink: #dfeae4;
      --link: #12543b;
      --ok-bg: #e3f0e9; --ok-ink: #14543a;
      --warn-bg: #fbeed2; --warn-ink: #6a4703;
      --err-bg: #fbe7e4; --err-ink: #7a2318;
      --unknown-bg: #e9edea;
      --hatch: #6f8178;
      /* type voices (spec §1.3) */
      --register: ui-monospace, "Cascadia Mono", "SF Mono", Consolas, "Roboto Mono", Menlo, monospace;
      --body: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      font-family: var(--body);
      font-size: 16px;
      line-height: 1.5;
      color: var(--ink);
      background: var(--ground);
    }
    * { box-sizing: border-box; }
    body { margin: 0; }
    [hidden] { display: none !important; }
    .visually-hidden { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
    .skip { position: absolute; left: -9999px; top: 0; background: var(--panel); color: var(--link); padding: 10px 14px; z-index: 5; }
    .skip:focus { left: 8px; top: 8px; }
    :focus-visible { outline: 3px solid var(--caution); box-shadow: 0 0 0 1px var(--ink); outline-offset: 1px; }
    .table-wrap:focus-visible { outline-offset: -3px; }
    a { color: var(--link); }
    a:hover { text-decoration-thickness: 2px; }

    /* header plate */
    header { background: var(--housing); color: white; border-bottom: 5px solid var(--caution); }
    header div, main, .tabs { width: min(1080px, calc(100% - 32px)); margin: auto; }
    header div { padding: 26px 0 20px; }
    h1 { margin: 0; font-family: var(--register); font-size: 1.9rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; text-wrap: balance; }
    header p { margin: 8px 0 0; max-width: 78ch; color: var(--brand-ink); }
    header small, header p small { color: var(--brand-ink); }
    header time { color: white; }

    /* mode selector */
    nav.tabs-outer { background: var(--housing); }
    .tabs { display: flex; flex-wrap: wrap; gap: 2px; padding-bottom: 0; }
    .tabs a { color: var(--brand-ink); text-decoration: none; padding: 10px 13px; font-size: .78rem; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; border-bottom: 3px solid transparent; touch-action: manipulation; }
    .tabs a:hover { color: white; }
    .tabs a[aria-current] { color: white; background: rgba(255,255,255,.1); border-bottom-color: var(--caution); }

    main { padding: 22px 0 48px; }
    section { scroll-margin-top: 12px; }
    h2 { font-size: 1.3rem; margin: 26px 0 6px; text-wrap: balance; }
    .panel > h2:first-child { margin-top: 4px; }
    h3 { font-size: 1.02rem; margin: 22px 0 6px; }
    h4 { font-size: .78rem; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: var(--ink-soft); margin: 20px 0 6px; }
    p { margin: 8px 0; max-width: 78ch; }
    small { color: var(--ink-soft); }
    .lede, .definition, .label, .denominator { color: var(--ink-soft); font-size: .9rem; }
    .definition { margin: 4px 0 10px; }
    .denominator { margin: 6px 0 8px; padding-left: 10px; border-left: 2px solid var(--signal); font-family: var(--register); font-size: .84rem; }

    /* annunciator lamps (spec §3.2) */
    .lamps { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 10px; }
    .lamp { display: inline-flex; align-items: center; gap: 7px; font-size: .74rem; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; padding: 3px 9px; border: 1px solid transparent; white-space: nowrap; }
    .lamp .bulb { width: 8px; height: 8px; flex: none; }
    .lamp.ok { background: var(--ok-bg); color: var(--ok-ink); border-color: #bcd9c9; }
    .lamp.ok .bulb { background: var(--ok-ink); }
    .lamp.warn { background: var(--warn-bg); color: var(--warn-ink); border-color: #e0c179; }
    .lamp.warn .bulb { background: var(--warn-ink); }
    .lamp.err { background: var(--err-bg); color: var(--err-ink); border-color: #e0b0a8; }
    .lamp.err .bulb { background: var(--err-ink); }
    .lamp.unknown { background: var(--unknown-bg); color: var(--ink-soft); border-color: var(--line); }
    .lamp.unknown .bulb { background: var(--ink-soft); }

    /* observation board (spec §3.3) */
    .board { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; margin: 14px 0 6px; }
    .card { border: 1.5px solid var(--housing); background: var(--panel); padding: 14px 16px 16px; min-width: 0; }
    .card-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
    .scope-name { margin: 0; font-family: var(--register); font-size: .88rem; font-weight: 600; overflow-wrap: anywhere; }
    .country-chip { font-family: var(--register); font-size: .72rem; border: 1px solid var(--line); padding: 0 6px; color: var(--ink-soft); }
    .card .count { font-family: var(--register); font-size: 1.6rem; font-weight: 600; line-height: 1.1; }
    .card .count small { display: block; font-family: var(--body); font-weight: 400; font-size: .78rem; margin-top: 2px; }
    .card .observed { font-size: .8rem; color: var(--ink-soft); margin: 2px 0 10px; }
    .frame-fig { margin: 10px 0 4px; }
    .frame-fig svg { display: block; height: auto; }
    .frame-fig .tick-on { fill: var(--signal); }
    .frame-fig .tick-off { fill: none; stroke: var(--ink-soft); stroke-width: 1; }
    .frame-fig .grad { stroke: var(--ink-soft); stroke-width: 1; }
    .frame-note { font-size: .78rem; color: var(--ink-soft); margin: 4px 0 0; }
    .trend-line { font-size: .8rem; color: var(--ink-soft); margin: 8px 0 0; padding-left: 10px; border-left: 2px solid var(--line); }

    /* mark key (spec §3.5) */
    .mark-key { list-style: none; margin: 10px 0; padding: 0; max-width: 78ch; }
    .mark-key li { display: flex; align-items: center; gap: 10px; margin: 4px 0; font-size: .88rem; }
    .mk { width: 26px; height: 14px; flex: none; border: 1px solid var(--line); }
    .mk.filled { background: var(--signal); border-color: var(--signal); }
    .mk.hollow { background: var(--panel); border: 1.5px solid var(--ink-soft); }
    .mk.hatched { background: repeating-linear-gradient(45deg, transparent 0 3px, var(--hatch) 3px 4.5px); }
    .mk.dashed { border: 1.5px dashed var(--ink-soft); background: transparent; }
    .mk-dot { display: inline-block; width: 11px; height: 11px; vertical-align: -1px; }

    /* scope plates (spec §3.1) */
    .scope-plate { border: 1.5px solid var(--housing); background: var(--panel); padding: 12px 16px 16px; margin: 14px 0 20px; }
    .scope-plate > .card-head { border-bottom: 1px solid var(--line-soft); padding-bottom: 8px; }

    /* stats readouts (spec §3.15) */
    .stats { display: flex; flex-wrap: wrap; gap: 12px; margin: 12px 0 6px; padding: 0; }
    .stats div { background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--signal); padding: 10px 14px; min-width: 12rem; }
    .stats dt { font-size: .72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--ink-soft); }
    .stats dd { margin: 3px 0 0; font-family: var(--register); font-size: 1.2rem; font-variant-numeric: tabular-nums; }
    .stats dd small { display: block; font-family: var(--body); font-size: .78rem; }

    /* filters and controls */
    .filters { display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: flex-end; background: var(--panel); border: 1px solid var(--line); padding: 12px 14px; margin: 0 0 14px; }
    .filters .field { display: flex; flex-direction: column; gap: 3px; }
    .filters label { font-size: .72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--ink-soft); }
    .filters select, .filters input { font: inherit; font-size: .88rem; padding: 5px 7px; border: 1px solid var(--line); background: var(--panel); color: var(--ink); min-width: 9rem; }
    .filters .actions { display: flex; gap: 8px; align-items: center; margin-left: auto; }
    button { font: inherit; font-size: .85rem; padding: 5px 10px; border: 1px solid var(--line); background: var(--panel); color: var(--link); cursor: pointer; touch-action: manipulation; }
    button:hover { border-color: var(--housing); }
    .live { min-height: 1.2em; font-size: .85rem; color: var(--ink-soft); margin: 0 0 12px; }

    /* tables (spec §3.8) */
    .block { margin: 12px 0 20px; }
    .block-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
    .table-wrap { overflow-x: auto; border: 1px solid var(--line); background: var(--panel); overscroll-behavior: contain; }
    table { width: 100%; border-collapse: collapse; min-width: 640px; }
    caption { text-align: left; padding: 12px 14px; font-size: .9rem; color: var(--ink-soft); }
    th, td { padding: 8px 14px; border-top: 1px solid var(--line-soft); text-align: left; white-space: nowrap; font-size: .92rem; }
    th { font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--ink-soft); background: #f8faf9; }
    tbody tr:hover { background: #f8faf9; }
    .count, td.count { text-align: right; font-family: var(--register); font-variant-numeric: tabular-nums; }
    td.wrap { white-space: normal; min-width: 20rem; font-size: .85rem; color: var(--ink-soft); }
    .bar-cell { width: 16%; min-width: 7rem; }
    .bar { display: block; height: 9px; background: var(--signal); min-width: 2px; }
    .bar-text { font-size: .74rem; color: var(--ink-soft); }
    td.state { border-left: 0; border-right: 0; color: var(--ink-soft); }
    .state { font-size: .88rem; padding: 10px 14px; margin: 8px 0; border: 1px solid var(--line); background: var(--panel); color: var(--ink-soft); }
    .state.error { background: var(--err-bg); color: var(--err-ink); border-color: #e0b0a8; }
    tr.filtered-empty td { color: var(--ink-soft); }

    /* suppressed cells: hatched ground on the word "suppressed" (spec §3.10) */
    td.suppressed { background: repeating-linear-gradient(45deg, transparent 0 3px, rgba(111, 129, 120, .5) 3px 4.5px); }

    /* mapping-strength chip (spec §3.7) */
    .chip { display: flex; align-items: center; gap: 8px; margin: 2px 0 8px; font-family: var(--register); font-size: .78rem; color: var(--ink-soft); }
    .chip .track { display: inline-flex; width: 96px; height: 12px; border: 1px solid var(--line); flex: none; }
    .chip .seg-on { background: var(--signal); }
    .chip .seg-half { background: repeating-linear-gradient(45deg, transparent 0 3px, var(--hatch) 3px 4.5px); }
    .chip .seg-off { background: var(--panel); }

    /* absence plate (spec §3.9) */
    .absence { border: 1.5px dashed var(--ink-soft); background: var(--panel); padding: 14px 16px; margin: 10px 0 16px; }
    .absence .eyebrow { font-size: .74rem; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: var(--ink-soft); display: flex; align-items: center; gap: 10px; margin: 0 0 6px; }
    .absence .dash { width: 34px; height: 0; border-top: 3px solid var(--ink-soft); flex: none; }
    .absence p { margin: 4px 0; font-size: .92rem; }

    /* sparkline (spec §3.12) */
    .spark { display: block; width: 100%; max-width: 720px; height: auto; background: var(--panel); border: 1px solid var(--line); }
    .spark .axis { stroke: var(--line); stroke-width: 1; }
    .spark polyline { fill: none; stroke: var(--signal); stroke-width: 2.5; stroke-linejoin: round; stroke-linecap: round; }
    .spark circle { fill: var(--signal); }

    .insight { margin: 6px 0; padding-left: 10px; border-left: 2px solid var(--ink-soft); max-width: 78ch; }
    .workflow { margin: 8px 0 4px; padding-left: 1.3em; max-width: 74ch; }
    .workflow li { margin: 3px 0; }
    .definitions { margin: 8px 0 4px; max-width: 78ch; }
    .definitions dt { font-weight: 600; margin-top: 8px; }
    .definitions dd { margin: 2px 0 0 1.2em; color: var(--ink-soft); font-size: .9rem; }
    .noscript-note { font-size: .88rem; }
    footer { margin-top: 22px; padding-top: 12px; border-top: 1px solid var(--line); color: var(--ink-soft); font-size: .85rem; }
    @media (max-width: 600px) {
      h1 { font-size: 1.25rem; }
      .board { grid-template-columns: 1fr; }
      .card .count { font-size: 1.4rem; }
      .filters .actions { margin-left: 0; }
      .filters select, .filters input { min-width: 0; width: 100%; }
      header div, main, .tabs { width: min(100% - 24px, 1080px); }
    }
    @media (prefers-reduced-motion: reduce) {
      * { animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; scroll-behavior: auto !important; }
    }
"""

# Progressive enhancement only: every section and row is server-rendered and visible
# without this script. Raw string: the JS escapes below are not Python escapes.
SCRIPT = r"""
(function () {
  "use strict";
  var KEYS = ["country", "source", "occupation", "skill", "from", "to"];
  var form = document.querySelector("[data-filters]");
  var live = document.querySelector("[data-live]");
  var loading = document.querySelector("[data-loading]");
  var failure = document.querySelector("[data-error]");
  var tabs = Array.prototype.slice.call(document.querySelectorAll("[data-tab]"));
  var panels = Array.prototype.slice.call(document.querySelectorAll("[data-panel]"));
  var rows = Array.prototype.slice.call(document.querySelectorAll("tbody tr[data-row]"));
  var section = "";

  function readHash() {
    var state = {};
    location.hash.replace(/^#/, "").split("&").forEach(function (pair) {
      var index = pair.indexOf("=");
      if (index < 1) return;
      var key = decodeURIComponent(pair.slice(0, index).replace(/\+/g, " "));
      state[key] = decodeURIComponent(pair.slice(index + 1).replace(/\+/g, " "));
    });
    return state;
  }

  function writeHash(state) {
    var parts = [];
    KEYS.concat(["section"]).forEach(function (key) {
      if (state[key]) parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(state[key]));
    });
    var hash = "#" + parts.join("&");
    try {
      history.replaceState(null, "", parts.length ? hash : location.href.split("#")[0]);
    } catch (ignored) {
      if (parts.length) location.hash = parts.join("&");
    }
  }

  function current() {
    var state = { section: section };
    KEYS.forEach(function (key) {
      var field = form ? form.elements[key] : null;
      if (field && field.value) state[key] = field.value;
    });
    return state;
  }

  function matches(row, state) {
    var data = row.dataset;
    if (state.country && data.country && data.country !== state.country) return false;
    if (state.source && data.source && data.source !== state.source) return false;
    if (state.occupation && data.dimension === "occupation" && data.value !== state.occupation) return false;
    if (state.skill && data.dimension === "skill" && data.value !== state.skill) return false;
    if (data.bucket && state.from && data.bucket < state.from) return false;
    if (data.bucket && state.to && data.bucket > state.to) return false;
    return true;
  }

  function apply(state) {
    var hiddenRows = 0;
    rows.forEach(function (row) {
      var show = matches(row, state);
      row.hidden = !show;
      if (!show) hiddenRows += 1;
    });
    Array.prototype.forEach.call(document.querySelectorAll("tr[data-filtered-empty]"), function (note) {
      var body = note.parentNode;
      var total = body.querySelectorAll("tr[data-row]").length;
      var shown = body.querySelectorAll("tr[data-row]:not([hidden])").length;
      note.hidden = !(total > 0 && shown === 0);
    });
    if (live) {
      live.textContent = hiddenRows
        ? "Filters hide " + hiddenRows + " of " + rows.length + " rows."
        : rows.length + " rows shown; no filters hide anything.";
    }
  }

  function activate(wanted) {
    var known = panels.filter(function (panel) { return panel.dataset.panel === wanted; });
    var target = known.length ? wanted : (panels.length ? panels[0].dataset.panel : "");
    panels.forEach(function (panel) { panel.hidden = panel.dataset.panel !== target; });
    tabs.forEach(function (tab) {
      if (tab.dataset.tab === target) tab.setAttribute("aria-current", "page");
      else tab.removeAttribute("aria-current");
    });
    return target;
  }

  function sync(fromHash) {
    if (loading) loading.hidden = false;
    try {
      var state = fromHash ? readHash() : current();
      if (fromHash && form) {
        KEYS.forEach(function (key) {
          var field = form.elements[key];
          if (field) field.value = state[key] || "";
        });
      }
      section = activate(state.section || section);
      state.section = section;
      apply(state);
      writeHash(state);
      if (failure) failure.hidden = true;
    } catch (problem) {
      rows.forEach(function (row) { row.hidden = false; });
      panels.forEach(function (panel) { panel.hidden = false; });
      if (failure) {
        failure.textContent = "Filters could not be applied (" + problem.message + "). Every row is shown instead.";
        failure.hidden = false;
      }
    } finally {
      if (loading) loading.hidden = true;
    }
  }

  function slug(text) {
    return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "table";
  }

  function field(text) {
    var value = String(text == null ? "" : text).replace(/\s+/g, " ").trim();
    return /[",]/.test(value) ? '"' + value.replace(/"/g, '""') + '"' : value;
  }

  function download(table) {
    var lines = [Array.prototype.map.call(table.querySelectorAll("thead th"), function (head) {
      return field(head.textContent);
    }).join(",")];
    Array.prototype.forEach.call(table.querySelectorAll("tbody tr[data-row]"), function (row) {
      if (row.hidden) return;
      lines.push(Array.prototype.map.call(row.cells, function (cell) { return field(cell.textContent); }).join(","));
    });
    var caption = table.querySelector("caption");
    var version = document.documentElement.getAttribute("data-methodology-version") || "";
    var link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([lines.join("\r\n") + "\r\n"], { type: "text/csv;charset=utf-8" }));
    link.download = slug(caption ? caption.textContent : table.id) + (version ? "-methodology-" + slug(version) : "") + ".csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(link.href); }, 0);
  }

  if (form) {
    form.hidden = false;
    form.addEventListener("change", function () { sync(false); });
    form.addEventListener("submit", function (event) { event.preventDefault(); sync(false); });
    var reset = form.querySelector("[data-reset]");
    if (reset) {
      reset.addEventListener("click", function () {
        KEYS.forEach(function (key) {
          var element = form.elements[key];
          if (element) element.value = "";
        });
        sync(false);
      });
    }
  }
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function (event) {
      event.preventDefault();
      section = tab.dataset.tab;
      sync(false);
      var panel = document.getElementById(section);
      if (panel) panel.focus();
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-csv]"), function (button) {
    button.hidden = false;
    button.addEventListener("click", function () {
      var table = document.getElementById(button.dataset.csv);
      if (table) download(table);
    });
  });
  window.addEventListener("hashchange", function () { sync(true); });
  sync(true);
})();
"""


def _count(value: int | None) -> str:
    """Render a possibly suppressed small-count cell: hatched ground on the word."""
    return f"{value:,}" if value is not None else "suppressed"


def _suppressed_class(value: int | None) -> str:
    """The cell class for a masked-view count: hatched ground when the group is withheld."""
    return " suppressed" if value is None else ""


def _stat(value: float | None) -> str:
    """Render an optional duration statistic; a dash reads better than 'suppressed' here."""
    return f"{value:.1f}" if value is not None else "—"


def _time(moment: datetime) -> str:
    return f'<time datetime="{moment.isoformat()}">{moment:%Y-%m-%d %H:%M} UTC</time>'


def _attrs(**values: str | None) -> str:
    """Mark a row as filterable and carry its escaped data-* filter keys."""
    keys = "".join(
        f' data-{key}="{escape(value, quote=True)}"' for key, value in values.items() if value
    )
    return f" data-row{keys}"


def _options(values: Iterable[str | None]) -> str:
    unique = sorted({value for value in values if value})
    return "".join(
        f'<option value="{escape(value, quote=True)}">{escape(value)}</option>' for value in unique
    )


def _definition(text: str) -> str:
    return f'<p class="definition">{escape(text)}</p>'


def _licence(reference: str | None) -> str:
    """A missing licence reference renders as a dash: an empty href is a broken self-link."""
    if not reference:
        return "—"
    return f'<a href="{escape(reference, quote=True)}">Licence</a>'


def _build_basis() -> str:
    """Name the rows this build read, so a synthetic page is never mistaken for a live one."""
    observations = os.environ.get("OBSERVATIONS_PATH", SAMPLE_OBSERVATIONS)
    if observations == SAMPLE_OBSERVATIONS:
        return "built from the synthetic sample in data/sample/"
    return f"built from stored collection partitions ({observations})"


def _badge(freshness_status: str, coverage_status: str) -> str:
    """Annunciator pair for table cells: word + numbers, never colour alone (spec §3.2)."""
    return f"{_lamp_freshness(freshness_status, None, None)} {_lamp_coverage(coverage_status)}"


def _lamp(tone: str, text: str, *, aria: bool = True) -> str:
    """One annunciator chip: a lamp bulb plus its Panel-Label text."""
    label = escape(text, quote=True) if aria else escape(text)
    return f'<span class="lamp {tone}"><span class="bulb" aria-hidden="true"></span>{label}</span>'


def _lamp_freshness(status: str, age_hours: float | None, threshold_hours: int | None) -> str:
    """Freshness lamp carrying its own numbers: age and threshold are always stated."""
    freshness = FRESHNESS_LABELS.get(status, status)
    if age_hours is not None and threshold_hours is not None:
        text = f"{freshness} · {age_hours:.0f} h old · threshold {threshold_hours} h"
    else:
        text = freshness
    tone = {"fresh": "ok", "stale": "warn"}.get(status, "unknown")
    return _lamp(tone, text)


def _lamp_coverage(status: str, observed: int | None = None, expected: int | None = None) -> str:
    """Coverage lamp: the row-count comparison is stated, not implied by tone."""
    coverage = COVERAGE_LABELS.get(status, status)
    if observed is not None and expected is not None:
        text = f"{coverage} · {observed:,} of {expected:,} rows"
    else:
        text = coverage
    tone = {"covered": "ok", "invalid": "err"}.get(status, "unknown")
    return _lamp(tone, text)


def _table(
    caption: str,
    columns: Sequence[tuple[str, bool]],
    body: str,
    *,
    name: str,
    empty: str,
) -> str:
    """Wrap a table in a focusable scroll region with a CSV control and both empty states."""
    heads = "".join(
        f'<th scope="col" class="{"count" if numeric else "text"}">{escape(label)}</th>'
        for label, numeric in columns
    )
    span = len(columns)
    fallback = f'<tr><td colspan="{span}" class="state">{escape(empty)}</td></tr>'
    filtered = (
        f'<tr hidden data-filtered-empty><td colspan="{span}" class="state">'
        "Every row in this table is hidden by the current filters.</td></tr>"
    )
    identifier = escape(f"table-{name}", quote=True)
    return (
        '<div class="block">'
        f'<div class="table-wrap" role="region" tabindex="0" aria-label="{escape(caption, quote=True)}">'
        f'<table id="{identifier}"><caption>{escape(caption)}</caption>'
        f"<thead><tr>{heads}</tr></thead><tbody>{body or fallback}{filtered}</tbody></table></div>"
        f'<div class="block-head"><button type="button" data-csv="{identifier}" hidden>Download CSV</button></div>'
        "</div>"
    )


def _panel(slug: str, heading: str, content: str) -> str:
    return (
        f'<section id="{slug}" class="panel" data-panel="{slug}" tabindex="-1" '
        f'aria-labelledby="{slug}-heading"><h2 id="{slug}-heading">{escape(heading)}</h2>'
        f"{content}</section>"
    )


def _sparkline(points: Sequence[float | None], label: str) -> str:
    """Fixed-viewBox inline SVG; gap buckets break the line instead of plotting zero."""
    known = [value for value in points if value is not None]
    if not known:
        return f'<p class="state">{escape(label)}: no plottable bucket, so no line is drawn.</p>'
    peak = max(known)
    scale = peak or 1.0
    span = max(len(points) - 1, 1)
    segments: list[list[str]] = [[]]
    for index, value in enumerate(points):
        if value is None:
            segments.append([])
            continue
        segments[-1].append(f"{16 + 688 * index / span:.1f},{144 - 128 * (value / scale):.1f}")
    lines = "".join(
        f'<polyline points="{" ".join(segment)}"></polyline>'
        for segment in segments
        if len(segment) > 1
    )
    dots = "".join(
        f'<circle cx="{point.split(",")[0]}" cy="{point.split(",")[1]}" r="3"></circle>'
        for segment in segments
        if len(segment) == 1
        for point in segment
    )
    desc = (
        f"{len(known)} plotted bucket(s), peak {peak:,.0f}, "
        f"{len(points) - len(known)} bucket(s) left as gaps because they are suppressed or were "
        "never observed. The exact values are listed in the table below this chart."
    )
    return (
        f'<svg class="spark" role="img" width="720" height="160" viewBox="0 0 720 160" aria-label="{escape(label, quote=True)}">'
        f"<title>{escape(label)}</title><desc>{escape(desc)}</desc>"
        '<line class="axis" x1="16" y1="144" x2="704" y2="144"></line>'
        f"{lines}{dots}</svg>"
    )


def _next_bucket(moment: datetime, grain: str) -> datetime:
    if grain == "month":
        carry, month = divmod(moment.month, 12)
        return moment.replace(year=moment.year + carry, month=month + 1, day=1)
    return moment + timedelta(days=7 if grain == "week" else 1)


def _active_series(series: Sequence[FlowRow], grain: str) -> list[float | None]:
    """Active postings on a bucket-stepped axis: a period the source never published is a gap."""
    values = {row[2]: row[5] for row in series}
    ordered = sorted(values)
    if not ordered:
        return []
    buckets = list(ordered)
    if grain in GRAIN_LABELS:
        buckets = [ordered[0]]
        while buckets[-1] < ordered[-1]:
            buckets.append(_next_bucket(buckets[-1], grain))
    points: list[float | None] = []
    for key in buckets:
        value = values.get(key)
        points.append(None if value is None else float(value))
    return points


def _finest_series(flows: Sequence[FlowRow]) -> tuple[str, list[FlowRow]]:
    """The headline trend uses the finest grain actually published."""
    for grain in ("day", "week", "month"):
        selected = [row for row in flows if row[1] == grain]
        if selected:
            return grain, selected
    return "", []


def _direction(values: Sequence[int | None]) -> str:
    known = [value for value in values if value is not None]
    if len(known) < 2:
        return "too few unsuppressed buckets to state a direction"
    first, last = known[0], known[-1]
    if last > first:
        return f"rising within the source ({first:,} to {last:,})"
    if last < first:
        return f"falling within the source ({first:,} to {last:,})"
    return f"flat within the source ({last:,})"


def _query_demand(connection: duckdb.DuckDBPyConnection) -> list[DemandRow]:
    rows: list[DemandRow] = connection.execute(
        """
        select source, scope_id, country, observed_at, active_postings, source_version,
               licence_reference, access_method, freshness_status, coverage_status
        from labour_demand_latest
        order by active_postings desc, source, country
        """
    ).fetchall()
    return rows


def _query_coverage(connection: duckdb.DuckDBPyConnection) -> list[CoverageRow]:
    """One row per source scope: source_coverage keeps every sweep, the section shows the latest."""
    rows: list[CoverageRow] = connection.execute(
        """
        select source, scope_id, country, observed_at, expected_rows, observed_rows,
               freshness_status, coverage_status, freshness_age_hours, coverage_limitations,
               freshness_threshold_hours
        from source_coverage
        qualify row_number() over (
            partition by source, scope_id order by observed_at desc, sweep_id desc
        ) = 1
        order by source, scope_id, country, observed_at desc
        """
    ).fetchall()
    return rows


def _query_region_breadth(connection: duckdb.DuckDBPyConnection) -> list[RegionBreadthRow]:
    """Region breadth per scope: distinct mapped NUTS-3 codes against the pinned frame.

    This cannot come from the rendered region rows: _query_dimension truncates the ranking at
    DIMENSION_LIMIT per scope, and the live German scope has 393 region rows of which 25 are
    published. The view counts what the ranking would have listed, not what fits on the page.
    """
    rows: list[RegionBreadthRow] = connection.execute(
        """
        select source, scope_id, country, regions_with_postings, regions_in_frame
        from region_breadth_latest
        order by source, scope_id
        """
    ).fetchall()
    return rows


def _query_dimension(
    connection: duckdb.DuckDBPyConnection, *, region: bool
) -> list[ScopedDimensionRow]:
    """Region rows feed Countries; everything else feeds Occupations and skills.

    DIMENSION_LIMIT applies per scope: `qualify` ranks inside each (source, scope_id), so
    one busy scope cannot crowd another scope's values out of its own top list.
    """
    comparison = "=" if region else "<>"
    rows: list[ScopedDimensionRow] = connection.execute(
        f"""
        select source, scope_id, dimension, value_label, taxonomy_version, posting_count
        from dimension_demand_latest
        where dimension {comparison} 'region'
        qualify row_number() over (
            partition by source, scope_id, dimension order by posting_count desc, value_label
        ) <= {DIMENSION_LIMIT}
        order by source, scope_id, posting_count desc, dimension, value_label
        """
    ).fetchall()
    return rows


def _query_skills(connection: duckdb.DuckDBPyConnection) -> list[ScopedDimensionRow]:
    rows: list[ScopedDimensionRow] = connection.execute(
        f"""
        select source, scope_id, dimension, value_label, taxonomy_version, posting_count
        from skill_demand_latest
        qualify row_number() over (
            partition by source, scope_id, dimension order by posting_count desc, value_label
        ) <= {DIMENSION_LIMIT}
        order by source, scope_id, posting_count desc, value_label
        """
    ).fetchall()
    return rows


def _query_mapping(connection: duckdb.DuckDBPyConnection) -> list[ScopedMappingRow]:
    """Per-scope mapping outcomes. The sum is within one scope only: summing across scopes
    would publish a figure belonging to no sweep at all."""
    rows: list[ScopedMappingRow] = connection.execute(
        "select source, scope_id, dimension, mapping_status, sum(outcome_count)::bigint "
        "from mapping_quality_latest "
        "group by source, scope_id, dimension, mapping_status "
        "order by source, scope_id, dimension, mapping_status"
    ).fetchall()
    return rows


def _query_requirements(connection: duckdb.DuckDBPyConnection) -> list[ScopedRequirementRow]:
    """Three closed-vocabulary distributions. No limit: at most six values cannot truncate, and a
    truncated distribution would stop summing to the sweep it was drawn from.

    `value_code` is the final tiebreak because two unmapped codes share the label
    `Unrecognised code`, so label alone is not a total order and their published order would be
    whatever the engine happened to produce."""
    rows: list[ScopedRequirementRow] = connection.execute(
        """
        select source, scope_id, dimension, value_label, value_code, mapping_status, posting_count
        from requirement_demand_latest
        order by source, scope_id, dimension, posting_count desc, value_label, value_code
        """
    ).fetchall()
    return rows


def _query_mapping_coverage(
    connection: duckdb.DuckDBPyConnection,
) -> list[MappingCoverageRow]:
    """The denominator for every ranking: postings observed, offered, and usable per dimension."""
    rows: list[MappingCoverageRow] = connection.execute(
        """
        select source, scope_id, dimension, postings_total, postings_with_source_value,
               postings_mapped
        from mapping_coverage_latest
        order by source, scope_id, dimension
        """
    ).fetchall()
    return rows


def _scope_keys(demand: Sequence[DemandRow]) -> list[ScopeKey]:
    """Ordered (source, scope_id) subsections, in demand order so the largest scope leads.

    An empty demand still renders one fallback subsection: the ranked tables and their
    denominators must exist even on a page with no postings, because the release check fails a
    ranked table that disappears entirely.
    """
    keys: list[ScopeKey] = []
    for row in demand:
        key = (row[0], row[1])
        if key not in keys:
            keys.append(key)
    return keys or [("", "")]


def _scope_slug(source: str, scope_id: str) -> str:
    """A stable id fragment for one scope's tables; unique per (source, scope_id) pair."""
    text = re.sub(r"[^a-z0-9]+", "-", f"{source}-{scope_id}".lower()).strip("-")
    return text[:60] or "scope"


def _scope_label(source: str, scope_id: str) -> str:
    return f"{source} / {scope_id}" if source or scope_id else "No collecting scope"


def _scope_plate(source: str, scope_id: str, country: str | None, suffix: str, body: str) -> str:
    """The bounded plate for one (source, scope_id): name as a real h3, one country chip.

    The plate name must be an h3, not a styled span: the page's heading ladder is
    h2 section -> h3 scope -> h4 sub-block, and release_check fails skipped levels.
    `translate="no"` keeps auto-translation from garbling code tokens such as
    `jobtech-f5cf1d409aa51fad`.
    """
    slug = _scope_slug(source, scope_id)
    label = _scope_label(source, scope_id)
    chip = f'<span class="country-chip" translate="no">{escape(country)}</span>' if country else ""
    return (
        f'<article class="scope-plate" aria-labelledby="plate-{slug}-{suffix}">'
        f'<div class="card-head"><h3 class="scope-name" translate="no" '
        f'id="plate-{slug}-{suffix}">{escape(label)}</h3>{chip}</div>'
        f"{body}</article>"
    )


def _lamps_for(row: Sequence[object]) -> str:
    """Both annunciators for one coverage row, numbers included (freshness then coverage).

    An empty row (no coverage published) renders the unknown-usage pair: absence of
    coverage data is itself the state to state, not a crash.
    """
    if len(row) < 11:
        return (
            '<div class="lamps">'
            + _lamp_freshness("unknown", None, None)
            + " "
            + _lamp_coverage("unknown_metadata")
            + "</div>"
        )
    expected, observed = row[4], row[5]
    freshness, coverage = row[6], row[7]
    age, threshold = row[8], row[10]
    lamps = _lamp_freshness(
        str(freshness),
        age if isinstance(age, float) else None,
        threshold if isinstance(threshold, int) else None,
    )
    lamps += " " + _lamp_coverage(
        str(coverage),
        observed if isinstance(observed, int) else None,
        expected if isinstance(expected, int) else None,
    )
    return f'<div class="lamps">{lamps}</div>'


def _frame_strip(row: RegionBreadthRow | None, *, context: str = "") -> str:
    """The unit-tick strip for one scope's breadth (spec §1.5/§3.4), as honest SVG.

    Frames of <= 60 regions render one tick per region; larger frames render two
    pattern-filled runs (filled for regions_with_postings cells, hollow for the rest)
    plus ruler graduations. The printed sentence is the breadth sentence itself,
    carried by aria-label and <desc> so the figure never replaces the words. The
    pattern ids carry a `context` suffix because one scope's strip renders in more
    than one place (board card and region plate), and ids must stay unique.
    """
    if row is None:
        return ""
    _source, _scope_id, country, with_postings, in_frame = row
    if in_frame is None or in_frame == 0 or with_postings is None:
        return ""
    text = (
        f"{with_postings:,} of {in_frame:,} {country} NUTS-3 regions have at least one "
        "mapped posting."
    )
    title = escape(text)
    if in_frame <= 60:
        pitch, unit = 36, 28
        width = in_frame * pitch - (pitch - unit)
        ticks = "".join(
            f'<rect class="{"tick-on" if index < with_postings else "tick-off"}" '
            f'x="{index * pitch}" y="4" width="{unit}" height="14"></rect>'
            for index in range(in_frame)
        )
        return (
            f'<figure class="frame-fig"><svg viewBox="0 0 {width} 22" width="{width}" '
            f'style="max-width:100%" role="img" aria-label="{title}">'
            f"<title>{title}</title>"
            f"<desc>One tick per region in the pinned {in_frame}-region NUTS-3 frame; filled "
            f"ticks are regions with at least one mapped posting, hollow ticks are regions "
            "the sweep did not reach.</desc>"
            f"<g>{ticks}</g></svg></figure>"
        )
    cell, height = 4, 14
    width = in_frame * cell
    on_width = with_postings * cell
    slug = re.sub(r"[^a-z0-9]+", "-", f"{country or 'xx'}-{in_frame}-{context}".lower())
    grads_every = 100
    lines = "".join(
        f'<line class="grad" x1="{mark}" y1="0" x2="{mark}" y2="22" stroke-width="0.8"></line>'
        for mark in range(grads_every, width, grads_every)
    )
    return (
        f'<figure class="frame-fig"><svg viewBox="0 0 {width} 22" width="{width}" '
        f'style="max-width:100%" role="img" aria-label="{title}">'
        f"<title>{title}</title>"
        f"<desc>One tick per region in the pinned {in_frame}-region NUTS-3 frame, at unit "
        "pitch: filled ticks are regions with at least one mapped posting, hollow ticks are "
        "regions the sweep did not reach. Ruler graduations every "
        f"{grads_every} regions.</desc>"
        f'<defs><pattern id="tick-on-{slug}" width="{cell}" height="{height}" '
        f'patternUnits="userSpaceOnUse"><rect x="0.4" y="0" width="2.6" height="{height}" '
        f'fill="var(--signal)"></rect></pattern>'
        f'<pattern id="tick-off-{slug}" width="{cell}" height="{height}" '
        f'patternUnits="userSpaceOnUse"><rect x="0.4" y="0" width="2.6" height="{height}" '
        f'fill="none" stroke="var(--ink-soft)" stroke-width="0.7"></rect></pattern></defs>'
        f'<rect x="0" y="4" width="{on_width}" height="{height}" '
        f'fill="url(#tick-on-{slug})"></rect>'
        f'<rect x="{on_width}" y="4" width="{width - on_width}" height="{height}" '
        f'fill="url(#tick-off-{slug})"></rect>'
        f"{lines}</svg></figure>"
    )


MARK_KEY = (
    '<ul class="mark-key" aria-label="Mark key">'
    '<li><span class="mk filled" aria-hidden="true"></span> '
    "Counted: observed and published by this sweep.</li>"
    '<li><span class="mk hollow" aria-hidden="true"></span> '
    "In the frame, not reached: within the pinned reference frame, with no mapped posting.</li>"
    '<li><span class="mk hatched" aria-hidden="true"></span> '
    "Withheld: a real group of 1 to 4 postings, suppressed for disclosure control.</li>"
    '<li><span class="mk dashed" aria-hidden="true"></span> '
    "Structurally absent: the source publishes no field for this, so nothing can be observed."
    "</li></ul>"
)


def _absence_plate(eyebrow: str, sentence: str, drawn_from: str = "") -> str:
    """The dashed plate that replaces a ranking table the source cannot feed (spec §3.9)."""
    denominator = f'<p class="denominator">{escape(drawn_from)}</p>' if drawn_from else ""
    return (
        f'<div class="absence"><p class="eyebrow"><span class="dash" aria-hidden="true">'
        f"</span>{escape(eyebrow)}</p><p>{escape(sentence)}</p>{denominator}</div>"
    )


def _mapping_chip(
    coverage: Sequence[MappingCoverageRow], scope: ScopeKey, dimension: str, noun: str
) -> str:
    """Mapping-strength chip beside a ranking: three segments plus printed counts (spec §3.7).

    Segments are scaled within the dimension's own postings_total, a rendering of counts
    the denominator sentence already states, so the chip can never contradict it.
    """
    row = next(
        (
            entry
            for entry in coverage
            if (entry[0], entry[1]) == scope and entry[2] == dimension and entry[3] > 0
        ),
        None,
    )
    if row is None:
        return ""
    total, with_value, mapped = row[3], row[4], row[5]

    def pct(count: int) -> float:
        return max(100 * count / total, 1) if count else 0

    label = (
        f"Mapping strength: {mapped:,} of {total:,} postings mapped; {with_value:,} carry a "
        f"structured {noun} field."
    )
    return (
        f'<p class="chip" aria-label="{escape(label, quote=True)}">'
        f'<span class="track" aria-hidden="true"><span class="seg-on" '
        f'style="width:{pct(mapped):.1f}%"></span>'
        f'<span class="seg-half" style="width:{pct(with_value - mapped):.1f}%"></span>'
        f'<span class="seg-off" style="width:{pct(total - with_value):.1f}%"></span></span>'
        f"{mapped:,} mapped · {with_value:,} carry the field · {total:,} in the sweep</p>"
    )


def _group_dimensions(
    rows: Sequence[ScopedDimensionRow],
) -> dict[ScopeKey, list[DimensionRow]]:
    grouped: dict[ScopeKey, list[DimensionRow]] = {}
    for source, scope_id, dimension, label, taxonomy_version, count in rows:
        grouped.setdefault((source, scope_id), []).append(
            (dimension, label, taxonomy_version, count)
        )
    return grouped


def _group_mapping(rows: Sequence[ScopedMappingRow]) -> dict[ScopeKey, list[MappingRow]]:
    grouped: dict[ScopeKey, list[MappingRow]] = {}
    for source, scope_id, dimension, status, count in rows:
        grouped.setdefault((source, scope_id), []).append((dimension, status, count))
    return grouped


def _group_requirements(
    rows: Sequence[ScopedRequirementRow],
) -> dict[ScopeKey, list[RequirementRow]]:
    grouped: dict[ScopeKey, list[RequirementRow]] = {}
    for source, scope_id, dimension, label, code, status, count in rows:
        grouped.setdefault((source, scope_id), []).append((dimension, label, code, status, count))
    return grouped


def _query_flows(connection: duckdb.DuckDBPyConnection) -> list[FlowRow]:
    rows: list[FlowRow] = connection.execute(
        """
        select scope_id, grain, bucket_start, openings, closures, active_postings,
               active_vacancies, source
        from posting_flows
        order by source, scope_id, case grain when 'day' then 1 when 'week' then 2 else 3 end,
                 bucket_start
        """
    ).fetchall()
    return rows


def _query_survival(connection: duckdb.DuckDBPyConnection) -> list[SurvivalRow]:
    rows: list[SurvivalRow] = connection.execute(
        """
        select scope_id, lifecycle_status, any_right_censored, posting_count, advertised_vacancies,
               median_duration_days, p25_duration_days, p75_duration_days, max_duration_days, source
        from posting_survival
        order by source, scope_id,
                 case lifecycle_status when 'active' then 1 when 'source_reported' then 2 else 3 end
        """
    ).fetchall()
    return rows


def _query_frequency(connection: duckdb.DuckDBPyConnection) -> list[FrequencyRow]:
    rows: list[FrequencyRow] = connection.execute(
        """
        select scope_id, complete_sweeps, first_observed_at, last_observed_at,
               median_interval_hours, freshness_threshold_hours, coverage_limitations, source
        from collection_frequency
        order by source, scope_id
        """
    ).fetchall()
    return rows


def _query_provenance(connection: duckdb.DuckDBPyConnection) -> list[ProvenanceRow]:
    rows: list[ProvenanceRow] = connection.execute(
        """
        select source, scope_id, observed_at, licence_reference, access_method, source_version,
               nuts_version, jobtech_taxonomy_version, esco_version, row_count
        from latest_complete_sweeps
        order by source, scope_id
        """
    ).fetchall()
    return rows


def _render_filters(
    demand: Sequence[DemandRow],
    occupations: Sequence[DimensionRow],
    skills: Sequence[DimensionRow],
) -> str:
    """Persistent filter bar. Hidden until the script enables it, because it needs JS to work."""
    countries = _options(row[2] for row in demand)
    sources = _options(row[0] for row in demand)
    occupation_values = _options(row[1] for row in occupations)
    skill_values = _options(row[1] for row in skills)
    return (
        '<form class="filters" data-filters hidden aria-label="Filter the published aggregates">'
        '<div class="field"><label for="filter-from">Buckets from</label>'
        '<input type="date" id="filter-from" name="from"></div>'
        '<div class="field"><label for="filter-to">Buckets to</label>'
        '<input type="date" id="filter-to" name="to"></div>'
        '<div class="field"><label for="filter-country">Country</label>'
        f'<select id="filter-country" name="country"><option value="">All countries</option>{countries}</select></div>'
        '<div class="field"><label for="filter-source">Source</label>'
        f'<select id="filter-source" name="source"><option value="">All sources</option>{sources}</select></div>'
        '<div class="field"><label for="filter-occupation">Occupation</label>'
        f'<select id="filter-occupation" name="occupation"><option value="">All occupations</option>{occupation_values}</select></div>'
        '<div class="field"><label for="filter-skill">Skill</label>'
        f'<select id="filter-skill" name="skill"><option value="">All skills</option>{skill_values}</select></div>'
        '<div class="actions"><button type="submit">Apply filters</button>'
        '<button type="button" data-reset>Reset filters</button></div>'
        "</form>"
        '<p class="state" data-loading hidden>Applying filters…</p>'
        '<p class="state error" data-error hidden></p>'
        '<p class="live" data-live role="status" aria-live="polite"></p>'
        '<noscript><p class="state">Filters, section tabs, and CSV download need JavaScript. '
        "Every section and every row is already rendered below without it.</p></noscript>"
    )


def _insight_paragraph(text: str) -> str:
    """One generated sentence, server-rendered and escaped like every other string."""
    return f'<p class="insight">{escape(text)}</p>'


def _insights_by_scope(
    section_insights: Sequence[insights.Insight],
) -> dict[str, list[insights.Insight]]:
    """Group one section's insights by the scope each sentence describes."""
    grouped: dict[str, list[insights.Insight]] = {}
    for insight in section_insights:
        grouped.setdefault(insight.scope, []).append(insight)
    return grouped


def _insight_groups(
    grouped: Mapping[str, Sequence[insights.Insight]],
    labels: Mapping[str, str],
) -> str:
    """Labelled insight groups, for sections without per-scope subsections of their own.

    The scope label is markup beside the sentences, never inside them: a scope id such as
    `jobtech-f5cf1d409aa51fad` inside `Insight.text` would read as an unsourced number to
    the traceability test, and two scopes' sentences must never be readable as one.
    """
    return "".join(
        f'<p class="label">{escape(labels.get(scope, scope))}</p>'
        + "".join(_insight_paragraph(insight.text) for insight in group)
        for scope, group in grouped.items()
    )


def _observation_board(
    demand: Sequence[DemandRow],
    coverage: Sequence[CoverageRow],
    flows: Sequence[FlowRow],
    frequency: Sequence[FrequencyRow],
    breadth_by_scope: Mapping[ScopeKey, RegionBreadthRow],
) -> str:
    """One instrument card per (source, scope_id); nothing pools across cards (spec §2.3).

    The board replaces the old "Largest single observation" hero stat, which invited
    exactly the cross-scope comparison the page forbids. Every card reads its own
    scope's demand row, coverage lamps, breadth strip, and trend state.
    """
    coverage_by_scope: dict[str, Sequence[object]] = {}
    for row in coverage:
        coverage_by_scope.setdefault(row[1], row)
    sweeps_by_scope = {row[0]: row[1] for row in frequency}
    published = {row[0] for row in flows}
    cards: list[str] = []
    for source, scope_id, country, observed_at, active, *_rest in demand:
        lamps = _lamps_for(coverage_by_scope.get(scope_id, ()))
        strip = _frame_strip(breadth_by_scope.get((source, scope_id)), context="card")
        note = _breadth_note(breadth_by_scope.get((source, scope_id)))
        if scope_id in published:
            grain, series = _finest_series([row for row in flows if row[0] == scope_id])
            direction = _direction([row[5] for row in series])
            sweeps = sweeps_by_scope.get(scope_id, 0)
            trend = (
                f"{GRAIN_LABELS.get(grain, 'No grain')} · {direction} · {sweeps} complete sweeps"
            )
        else:
            trend = "no trend published for this scope"
        cards.append(
            f'<article class="card" aria-labelledby="card-{_scope_slug(source, scope_id)}">'
            f'<div class="card-head"><h3 class="scope-name" translate="no" '
            f'id="card-{_scope_slug(source, scope_id)}">'
            f"{escape(_scope_label(source, scope_id))}</h3>"
            f'<span class="country-chip" translate="no">{escape(country or "")}</span></div>'
            f"{lamps}"
            f'<p class="count">{active:,}<small>active postings · this scope only</small></p>'
            f'<p class="observed">Observed {_time(observed_at)}</p>'
            f"{strip}{note}"
            f'<p class="trend-line">{escape(trend)}</p>'
            "</article>"
        )
    return f'<h3>The observation board</h3><div class="board">{"".join(cards)}</div>'


def _breadth_note(row: RegionBreadthRow | None) -> str:
    """The frame-note line under a board card's strip: the breadth sentence itself."""
    if row is None:
        return ""
    _source, _scope_id, country, with_postings, in_frame = row
    if in_frame is None or in_frame == 0 or with_postings is None:
        return ""
    return f'<p class="frame-note">{
        escape(
            f"{with_postings:,} of {in_frame:,} {country} NUTS-3 "
            "regions have at least one mapped posting."
        )
    }</p>'


def _render_overview(
    demand: Sequence[DemandRow],
    coverage: Sequence[CoverageRow],
    flows: Sequence[FlowRow],
    frequency: Sequence[FrequencyRow],
    breadth_by_scope: Mapping[ScopeKey, RegionBreadthRow],
    digest: str,
) -> str:
    steps = "".join(f"<li>{escape(step)}</li>" for step in WORKFLOW)
    updated = max((row[3] for row in demand), default=None)
    fresh = sum(1 for row in coverage if row[6] == "fresh")
    covered = sum(1 for row in coverage if row[7] == "covered")
    stats = (
        f"<div><dt>Last successful update</dt><dd>{_time(updated) if updated else '—'}"
        "<small>Latest approved complete sweep</small></dd></div>"
    )
    stats += (
        f"<div><dt>Source coverage</dt><dd>{covered} of {len(coverage)}"
        f"<small>source scope(s) covered · {fresh} fresh</small></dd></div>"
    )
    body = "".join(
        f"<tr{_attrs(country=country, source=source)}>"
        f"<td><strong>{escape(country or 'No postings')}</strong></td>"
        f"<td>{escape(source)}</td><td>{_time(observed_at)}</td>"
        f'<td class="count">{active:,}</td>'
        f"<td>{_badge(freshness_status, coverage_status)}</td></tr>"
        for (
            source,
            _scope_id,
            country,
            observed_at,
            active,
            _source_version,
            _licence_reference,
            _access_method,
            freshness_status,
            coverage_status,
        ) in demand
    )
    return (
        '<p class="lede">A quiet, aggregate record of public technology job-posting demand. '
        "Counts are not summed or deduplicated across sources, and nothing here is real time: "
        "every figure comes from the latest approved complete sweep.</p>"
        + _observation_board(demand, coverage, flows, frequency, breadth_by_scope)
        + "<h3>How to read this page</h3>"
        + MARK_KEY
        + f'<ol class="workflow">{steps}</ol>'
        "<h3>Where the data stands now</h3>"
        f'<dl class="stats">{stats}</dl>'
        + digest
        + _definition(
            "Active postings are postings observed as open in the latest complete sweep for one "
            "source and scope. Freshness compares the observation age with the source threshold; "
            "coverage compares observed rows with expected rows. Latest-sweep counts are published "
            "in full; small-count suppression applies to the posting-flow and survival tables."
        )
        + _table(
            "Latest observed demand per source and scope",
            (
                ("Country", False),
                ("Source", False),
                ("Observed", False),
                ("Postings", True),
                ("Status", False),
            ),
            body,
            name="overview-demand",
            empty="No demand results",
        )
    )


def _run_state(row: CoverageRow) -> str:
    """One plain sentence per scope, worded from the conditions source_coverage actually tests."""
    age, threshold = row[8], row[10]
    age_text = f"is {age / 24:.1f} days old" if age is not None else "has an unknown age"
    if row[6] == "fresh":
        freshness = "which is inside the source freshness threshold"
    elif row[6] == "stale":
        freshness = (
            f"which is past the {threshold} hour freshness threshold, so read it as out of date"
            if threshold is not None
            else "which is past the source freshness threshold, so read it as out of date"
        )
    else:
        freshness = "and no freshness threshold is recorded for it"
    expected, observed = row[4], row[5]
    # source_coverage calls a sweep invalid for a shortfall, a surplus, or rows outside the
    # expected country, and reports missing approval or metadata ahead of either comparison.
    if observed < expected:
        stored = f"It stored {observed:,} of {expected:,} expected row(s), so rows are missing."
    elif observed > expected:
        stored = (
            f"It stored {observed:,} row(s) against {expected:,} expected, so it holds more than "
            "its own manifest."
        )
    elif row[7] == "invalid":
        stored = (
            f"It stored the expected {observed:,} row(s), but some of them fall outside the "
            "expected country."
        )
    else:
        stored = f"It stored all {observed:,} expected row(s)."
    if row[7] == "unknown_metadata":
        stored += " Coverage is uncertified because sweep approval or metadata is incomplete."
    return f"The last complete sweep {age_text}, {freshness}. {stored}"


def _render_status(
    coverage: Sequence[CoverageRow],
    frequency: Sequence[FrequencyRow],
    built: datetime,
    insights_html: str,
) -> str:
    """Operational run summary: what the last sweep did per scope and how to read that state."""
    cadence = {(row[7], row[0]): row for row in frequency}
    fresh = sum(1 for row in coverage if row[6] == "fresh")
    covered = sum(1 for row in coverage if row[7] == "covered")
    sweeps = sum(row[1] for row in frequency)
    stored_rows = sum(row[5] for row in coverage)
    latest = max((row[3] for row in coverage), default=None)
    stats = (
        f"<div><dt>Last complete sweep</dt><dd>{_time(latest) if latest else '—'}"
        f"<small>Across {len(coverage)} published source scope(s)</small></dd></div>"
        f"<div><dt>Fresh scopes</dt><dd>{fresh} of {len(coverage)}"
        "<small>Inside the source freshness threshold</small></dd></div>"
        f"<div><dt>Fully covered scopes</dt><dd>{covered} of {len(coverage)}"
        "<small>Manifest row count matched and sweep metadata complete</small></dd></div>"
        f"<div><dt>Complete sweeps published</dt><dd>{sweeps:,}"
        f"<small>{stored_rows:,} row(s) stored by the latest sweep of each scope</small></dd></div>"
        f"<div><dt>Page built</dt><dd>{_time(built)}"
        f"<small>Methodology version {escape(METHODOLOGY_VERSION)} · {escape(_build_basis())}</small>"
        "</dd></div>"
    )
    rows: list[str] = []
    for row in coverage:
        entry = cadence.get((row[0], row[1]))
        interval = entry[4] if entry else None
        days = None if row[8] is None else row[8] / 24
        rows.append(
            f"<tr{_attrs(country=row[2], source=row[0])}>"
            f"<td>{escape(row[0])}</td><td>{escape(row[1])}</td><td>{_time(row[3])}</td>"
            f'<td class="count">{_stat(days)}</td><td class="count">{row[5]:,}</td>'
            f'<td class="count">{_stat(interval)}</td>'
            f'<td class="count">{row[10] if row[10] is not None else "—"}</td>'
            f"<td>{_badge(row[6], row[7])}</td>"
            f'<td class="wrap">{escape(_run_state(row))}</td></tr>'
        )
    return (
        insights_html
        + '<p class="lede">Whether the figures on this page are current, per source and scope. '
        "A stale or partially covered scope stays published and labelled rather than hidden.</p>"
        + _definition(
            "Only sweeps whose own manifest reports a complete run are loaded, so a failed run is "
            "never published as data: it shows up here as an ageing last sweep or as a scope that "
            "is absent altogether. Approval and row-count problems are labelled rather than "
            "dropped, except in the demand table, which publishes covered scopes only. Stale data "
            "is the freshness alert; Partial coverage means the stored rows do not match the "
            "manifest count or some rows fall outside the expected country; Unknown coverage means "
            "the sweep is unapproved or its metadata is incomplete, so coverage is uncertified."
        )
        + f'<dl class="stats">{stats}</dl>'
        + _table(
            "Operational status of the latest complete sweep per source and scope",
            (
                ("Source", False),
                ("Scope", False),
                ("Last complete sweep", False),
                ("Age (days)", True),
                ("Rows stored", True),
                ("Median interval (h)", True),
                ("Freshness threshold (h)", True),
                ("Status", False),
                ("What this means", False),
            ),
            "".join(rows),
            name="status-runs",
            empty="No source scope has published a complete sweep yet",
        )
    )


def _render_countries(
    demand: Sequence[DemandRow],
    regions_by_scope: Mapping[ScopeKey, Sequence[DimensionRow]],
    coverage: Sequence[MappingCoverageRow],
    scopes: Sequence[ScopeKey],
    countries: Mapping[str, str],
    breadth_by_scope: Mapping[ScopeKey, RegionBreadthRow],
    limitations: Mapping[ScopeKey, str | None],
    section_insights: Mapping[str, Sequence[insights.Insight]] | None = None,
    coverage_rows: Sequence[CoverageRow] = (),
) -> str:
    # ponytail: one bar baseline per source, never page-wide, so the bar cannot imply a
    # between-source or between-country magnitude comparison.
    baselines: dict[str, int] = {}
    for row in demand:
        baselines[row[0]] = max(baselines.get(row[0], 0), row[4])
    body = "".join(
        f"<tr{_attrs(country=country, source=source)}>"
        f"<td><strong>{escape(country or 'No postings')}</strong></td>"
        f"<td>{escape(source)}</td><td>{escape(scope_id)}</td><td>{_time(observed_at)}</td>"
        f"<td>{_badge(freshness_status, coverage_status)}</td>"
        f'<td class="count">{active:,}</td>'
        f'<td class="bar-cell"><span class="bar" style="width:{100 * active / (baselines[source] or 1):.1f}%" aria-hidden="true"></span>'
        f'<span class="bar-text">{100 * active / (baselines[source] or 1):.0f}% of this source\u2019s largest scope</span></td>'
        "<td><small>Within-source only</small></td>"
        f"<td>{_licence(licence_reference)}"
        f"<br><small>{escape(access_method)} · {escape(source_version)}</small></td></tr>"
        for (
            source,
            scope_id,
            country,
            observed_at,
            active,
            source_version,
            licence_reference,
            access_method,
            freshness_status,
            coverage_status,
        ) in demand
    )
    region_blocks: list[str] = []
    for source, scope_id in scopes:
        rows = regions_by_scope.get((source, scope_id), [])
        regions_body = "".join(
            f"<tr{_attrs(dimension=dimension, value=label, source=source, country=countries.get(scope_id))}>"
            f"<td>{escape(label)}</td><td>{escape(taxonomy_version)}</td>"
            f'<td class="count">{count:,}</td></tr>'
            for dimension, label, taxonomy_version, count in rows
        )
        breadth = _region_breadth_sentence(breadth_by_scope.get((source, scope_id)))
        limitation = limitations.get((source, scope_id))
        caveat = f'<p class="definition">{escape(limitation)}</p>' if limitation is not None else ""
        scope_sentences = (
            "".join(
                _insight_paragraph(insight.text)
                for insight in (section_insights or {}).get(scope_id, [])
            )
            if section_insights is not None
            else ""
        )
        # One plate per scope (spec §2.3): lamps, strip, caveat, sentences, denominator, table.
        coverage_row = next(
            (row for row in coverage_rows if row[1] == scope_id),
            (),
        )
        region_blocks.append(
            _scope_plate(
                source,
                scope_id,
                countries.get(scope_id),
                "regions",
                _lamps_for(coverage_row)
                + _frame_strip(breadth_by_scope.get((source, scope_id)), context="regions")
                + breadth
                + caveat
                # A region ranking is one row per posting, so the truncation at DIMENSION_LIMIT is
                # material (25 of 393 German regions): the unlisted-tail sentence must be stated.
                + scope_sentences
                + _denominator(coverage, (source, scope_id), "region", "region", listed=rows)
                + _table(
                    "Latest mapped demand by NUTS region",
                    (("Region", False), ("Reference version", False), ("Postings", True)),
                    regions_body,
                    name=f"countries-regions-{_scope_slug(source, scope_id)}",
                    empty="No mapped region results",
                ),
            )
        )
    return (
        _definition(
            "One row per source and scope. Counts are not summed or deduplicated across sources, "
            "and absolute counts are not comparable between countries: each source has its own "
            "scope, keyword filter, and posting culture. The relative-volume bar is scaled against "
            "the largest scope of the same source only. Read direction of change within a source "
            "instead."
        )
        + _table(
            "Latest posting counts by country, with collection provenance",
            (
                ("Country", False),
                ("Source", False),
                ("Scope", False),
                ("Observed", False),
                ("Status", False),
                ("Postings", True),
                ("Relative volume", False),
                ("Comparability", False),
                ("Access", False),
            ),
            body,
            name="countries-demand",
            empty="No demand results",
        )
        + "<h3>NUTS regions</h3>"
        + _definition(
            "Mapped NUTS 2024 regions for the latest sweep of each collecting scope. Region "
            "counts come from structured source geography only, never from free text, and are "
            "a subset of that scope's country total."
        )
        + "".join(region_blocks)
    )


def _region_breadth_sentence(row: RegionBreadthRow | None) -> str:
    """How many NUTS-3 regions carry at least one mapped posting, against the pinned frame.

    A count, never a share: a percentage invites a coverage trend a single sweep cannot
    support. A missing frame degrades to an explicit sentence rather than a wrong denominator,
    and "N of 0" is never rendered. The country is named by its own code (DE, SE), never a
    scope id: digits in a scope id would read as an unsourced number.
    """
    if row is None:
        return (
            '<p class="definition">No region breadth was published for this scope, so no '
            "breadth count is stated.</p>"
        )
    _source, _scope_id, country, with_postings, in_frame = row
    text: str
    if in_frame is None or in_frame == 0:
        text = (
            "No NUTS-3 frame is pinned for this country in the reference data, so no breadth "
            "count is published."
        )
    else:
        text = (
            f"{with_postings:,} of {in_frame:,} {country} NUTS-3 regions have at least one "
            "mapped posting."
        )
    return f'<p class="definition">{escape(text)}</p>'


def _denominator(
    coverage: Sequence[MappingCoverageRow],
    scope: ScopeKey,
    dimension: str,
    noun: str,
    *,
    listed: Sequence[DimensionRow] | None = None,
) -> str:
    """State what a ranking is drawn from, so a top-25 list is never read as the whole sweep.

    Three counts, no ratio: a percentage invites a coverage trend that a single sweep cannot
    support. The class is on the paragraph so scripts/release_check.py can insist the sentence is
    still there next to each ranked table.

    The scope key names the sweep: a denominator borrowed from another scope would state a
    total this table's rows were never drawn from.

    Pass `listed` for a ranking whose rows are one-per-posting, where the column is supposed to
    account for every mapped posting. It stops doing so the moment the ranking truncates at
    DIMENSION_LIMIT, and a reader who adds the column then gets a smaller number than the
    sentence above it states. The shortfall is published rather than left to be discovered.
    """
    row = next(
        (
            entry
            for entry in coverage
            if (entry[0], entry[1]) == scope and entry[2] == dimension and entry[3] > 0
        ),
        None,
    )
    if row is None:
        text = (
            f"No coverage row was published for the latest sweep, so this {noun} ranking has no "
            "stated denominator."
        )
    else:
        total, with_source_value, mapped = row[3], row[4], row[5]
        text = (
            f"Ranked from {mapped:,} mapped posting(s) of {total:,} in the latest sweep; "
            f"{with_source_value:,} carry a structured {noun}."
        )
        if listed is not None:
            shown = sum(entry[3] for entry in listed)
            if shown < mapped:
                text += (
                    f" Only the {len(listed):,} most frequent {noun}s are listed below, "
                    f"accounting for {shown:,} of those mapped postings; the rest sit in "
                    "an unlisted tail."
                )
    return f'<p class="denominator">{escape(text)}</p>'


def _denominator_text(
    coverage: Sequence[MappingCoverageRow],
    scope: ScopeKey,
    dimension: str,
    noun: str,
    *,
    listed: Sequence[DimensionRow] | None = None,
) -> str:
    """The denominator sentence as plain text, for an absence plate's drawn-from line."""
    row = next(
        (
            entry
            for entry in coverage
            if (entry[0], entry[1]) == scope and entry[2] == dimension and entry[3] > 0
        ),
        None,
    )
    if row is None:
        return (
            f"No coverage row was published for the latest sweep, so this {noun} ranking has no "
            "stated denominator."
        )
    total, with_source_value, mapped = row[3], row[4], row[5]
    text = (
        f"Ranked from {mapped:,} mapped posting(s) of {total:,} in the latest sweep; "
        f"{with_source_value:,} carry a structured {noun}."
    )
    if listed is not None:
        shown = sum(entry[3] for entry in listed)
        if shown < mapped:
            text += (
                f" Only the {len(listed):,} most frequent {noun}s are listed below, "
                f"accounting for {shown:,} of those mapped postings; the rest sit in "
                "an unlisted tail."
            )
    return text


def _empty_by_construction(
    coverage: Sequence[MappingCoverageRow], scope: ScopeKey, noun: str
) -> str:
    """State, from mapping_coverage_latest alone, when a ranking is empty because the source
    publishes no structured field for it.

    The condition is postings_with_source_value = 0 with postings_total > 0: a data-derived
    statement, not a hardcoded source special case, so any future source with the same gap is
    described correctly. Rendered above the denominator and with class="definition", because
    release_check consumes the next class="denominator" paragraph for the ranked table.
    """
    row = next(
        (
            entry
            for entry in coverage
            if (entry[0], entry[1]) == scope and entry[2] == noun and entry[3] > 0
        ),
        None,
    )
    if row is None or row[4] != 0:
        return ""
    text = (
        f"This source publishes no structured {noun} field for this scope, so no posting here "
        f"can be mapped to an ESCO {noun}: the ranking is empty by construction, not by a "
        "mapping failure."
    )
    return f'<p class="definition">{escape(text)}</p>'


def _render_occupations(
    occupations_by_scope: Mapping[ScopeKey, Sequence[DimensionRow]],
    skills_by_scope: Mapping[ScopeKey, Sequence[DimensionRow]],
    mapping_by_scope: Mapping[ScopeKey, Sequence[MappingRow]],
    coverage: Sequence[MappingCoverageRow],
    scopes: Sequence[ScopeKey],
    section_insights: Mapping[str, Sequence[insights.Insight]],
    countries: Mapping[str, str],
) -> str:
    columns = (("Rank", True), ("Value", False), ("Reference version", False), ("Postings", True))

    def ranked(rows: Sequence[DimensionRow], source: str, scope_id: str) -> str:
        # Numbers start from 1 inside each scope's own section.
        return "".join(
            f"<tr{_attrs(dimension=dimension, value=label, source=source, country=countries.get(scope_id))}>"
            f'<td class="count">{rank}</td><td>{escape(label)}</td>'
            f"<td>{escape(taxonomy_version)}</td>"
            f'<td class="count">{count:,}</td></tr>'
            for rank, (dimension, label, taxonomy_version, count) in enumerate(rows, start=1)
        )

    blocks: list[str] = []
    for source, scope_id in scopes:
        key = (source, scope_id)
        slug = _scope_slug(source, scope_id)
        occupations = occupations_by_scope.get(key, [])
        skills = skills_by_scope.get(key, [])
        mapping_body = "".join(
            f"<tr{_attrs()}><td>{escape(dimension)}</td><td>{escape(status)}</td>"
            f'<td class="count">{count:,}</td></tr>'
            for dimension, status, count in mapping_by_scope.get(key, [])
        )
        # Absence plates replace rankings the source cannot feed (spec §3.9); the plate
        # carries the empty-by-construction sentence plus the drawn-from line.
        occupation_absent = _empty_by_construction(coverage, key, "occupation")
        skill_absent = _empty_by_construction(coverage, key, "skill")
        if occupation_absent:
            occupation_block = _absence_plate(
                "Occupation ranking — structurally absent",
                "This source publishes no structured occupation field for this scope, so no "
                "posting here can be mapped to an ESCO occupation: the ranking is empty by "
                "construction, not by a mapping failure.",
                _denominator_text(coverage, key, "occupation", "occupation"),
            )
        else:
            occupation_block = (
                "<h4>Occupation ranking</h4>"
                + _mapping_chip(coverage, key, "occupation", "occupation")
                + _denominator(coverage, key, "occupation", "occupation", listed=occupations)
                + _table(
                    "Ranked mapped demand by ESCO occupation",
                    columns,
                    ranked(occupations, source, scope_id),
                    name=f"occupations-ranked-{slug}",
                    empty="No mapped dimension results",
                )
            )
        if skill_absent:
            skill_block = _absence_plate(
                "Technology skills — structurally absent",
                "This source publishes no structured skill field for this scope, so no posting "
                "here can be mapped to an ESCO skill: the ranking is empty by construction, not "
                "by a mapping failure.",
                _denominator_text(coverage, key, "skill", "skill"),
            )
        else:
            skill_block = (
                "<h4>Technology skills</h4>"
                + _mapping_chip(coverage, key, "skill", "skill")
                + _denominator(coverage, key, "skill", "skill")
                + _table(
                    "Ranked mapped demand by ESCO skill",
                    columns,
                    ranked(skills, source, scope_id),
                    name=f"occupations-skills-{slug}",
                    empty="No mapped skill results",
                )
            )
        blocks.append(
            _scope_plate(
                source,
                scope_id,
                countries.get(scope_id),
                "occupations",
                "".join(
                    _insight_paragraph(insight.text)
                    for insight in section_insights.get(scope_id, [])
                )
                + occupation_block
                + skill_block
                + "<h4>Mapping quality</h4>"
                + _table(
                    "Mapping quality outcomes",
                    (("Dimension", False), ("Status", False), ("Outcomes", True)),
                    mapping_body,
                    name=f"occupations-mapping-{slug}",
                    empty="No mapping quality results",
                ),
            )
        )
    return (
        _definition(
            "Mappings use pinned reference data: NUTS 2024 regions, JobTech Taxonomy v30, and ESCO "
            "1.2.1. Only structured taxonomy fields are used; job titles and free text are never "
            "classified. Where the crosswalk offers several candidates for one source concept and "
            "exactly one of them is an exact match, that one is used; two or more exact matches "
            "are left unresolved, as is a set with none. Ambiguous, low-confidence, unmapped, and "
            "not-present values are excluded from mapped demand and shown separately as mapping "
            "quality. Each ranking and its denominator below belong to exactly one collecting "
            "scope; scopes are never summed."
        )
        + _definition(
            "Skill demand counts postings whose structured fields map to an ESCO skill. Historical "
            "movement is read from the trend section within one source; a skill can rise in share "
            "while the total posting count falls. A posting asking for several mapped skills is "
            "counted in every one of their rows, so the rows below count postings per skill and do "
            "not sum to the mapped-posting count stated beside each table."
        )
        + _definition(
            "Mapping outcomes for the latest sweep of each scope. Unmapped, ambiguous, "
            "low-confidence, and not-present outcomes stay distinct so that a missing value is "
            "never read as zero demand."
        )
        + "".join(blocks)
    )


def _render_requirements(
    requirements_by_scope: Mapping[ScopeKey, Sequence[RequirementRow]],
    scopes: Sequence[ScopeKey],
    section_insights: Mapping[str, Sequence[insights.Insight]],
    countries: Mapping[str, str],
    demand: Sequence[DemandRow] = (),
) -> str:
    """Three closed-vocabulary distributions, each accounting for every posting in its sweep.

    Unlike the rankings above, nothing here is filtered to mapped values and nothing is
    truncated, so no denominator sentence is needed: a null source value is published as
    `Not stated` and a code the reference does not carry as `Unrecognised code`, both counted,
    and each column therefore sums to its own scope's sweep by inspection.
    """
    demand_totals = list(demand)
    blocks: list[str] = []
    for source, scope_id in scopes:
        requirements = requirements_by_scope.get((source, scope_id), [])
        slug = _scope_slug(source, scope_id)
        demand_total = next(
            (row[4] for row in demand_totals if (row[0], row[1]) == (source, scope_id)), None
        )
        tables = ""
        for dimension_slug, heading, noun in REQUIREMENT_SECTIONS:
            dimension_rows = [row for row in requirements if row[0] == dimension_slug]
            if dimension_rows:
                tables += f"<h4>{escape(heading)}</h4>" + _table(
                    f"Latest postings by {noun}",
                    (("Value", False), ("Source code", False), ("Postings", True)),
                    "".join(
                        f"<tr{_attrs(dimension=dimension, value=label, source=source, country=countries.get(scope_id))}>"
                        + _requirement_label_cell(label)
                        + f"<td>{escape(code or '—')}</td>"
                        f'<td class="count">{count:,}</td></tr>'
                        for dimension, label, code, _status, count in dimension_rows
                    ),
                    name=f"requirements-{dimension_slug.replace('_', '-')}-{slug}",
                    empty=f"No {noun} results",
                )
            elif demand_total:
                # The scope has postings but not this dimension's rows: the source publishes
                # no field for it (condition b of the design spec's Flag 1 - requirement
                # emptiness plus a positive posting total).
                tables += _absence_plate(
                    f"{heading} — structurally absent",
                    f"This source publishes no structured {'-'.join(noun.split())} field for "
                    f"this scope, so no {noun} distribution exists for any of its "
                    f"{demand_total:,} postings: the table is empty by construction, not by "
                    "a collection failure.",
                )
            else:
                # No postings and no rows: the empty table with its fallback sentence still
                # renders, because a dropped table would disable its release rule.
                tables += f"<h4>{escape(heading)}</h4>" + _table(
                    f"Latest postings by {noun}",
                    (("Value", False), ("Source code", False), ("Postings", True)),
                    "",
                    name=f"requirements-{dimension_slug.replace('_', '-')}-{slug}",
                    empty=f"No {noun} results",
                )
        blocks.append(
            _scope_plate(
                source,
                scope_id,
                countries.get(scope_id),
                "requirements",
                "".join(
                    _insight_paragraph(insight.text)
                    for insight in section_insights.get(scope_id, [])
                )
                + tables,
            )
        )
    return (
        '<p class="lede">What the postings in the latest sweep actually offer: permanent or '
        "fixed-term, full or part time, and for how long.</p>"
        + _definition(
            "Read from three structured JobTech Taxonomy v30 fields on each posting — employment "
            "type, working-hours type, and duration — never from free text. The values are the "
            "source's own closed vocabularies; the labels shown are our English translations of "
            "the Swedish taxonomy labels, and the source concept id is printed beside each one so "
            "a label can be traced back. Every posting in a scope's sweep appears in exactly one "
            "row of each of that scope's tables, so each Postings column sums to that sweep's "
            "posting count. Not stated means the source did not state a value for that field, "
            "and is counted rather than dropped; Unrecognised code means the source used a value "
            "this reference does not carry yet, and it is published with its code so a vocabulary "
            "change cannot pass unseen. Counts are per posting, not per advertised vacancy, and "
            "are published in full without small-count suppression, as the other latest-sweep "
            "counts are."
        )
        + "".join(blocks)
    )


def _requirement_label_cell(label: str) -> str:
    """A requirement value cell carrying its epistemic mark (spec §3.11).

    `Not stated` rows get a hollow-dot marker; `Unrecognised code` rows a hatched
    swatch: form carries the state, the label carries the word.
    """
    if label == "Not stated":
        return f'<td><span class="mk hollow mk-dot" aria-hidden="true"></span> {escape(label)}</td>'
    if label == "Unrecognised code":
        return (
            f'<td><span class="mk hatched mk-dot" aria-hidden="true"></span> {escape(label)}</td>'
        )
    return f"<td>{escape(label)}</td>"


def _render_survival(
    survival: Sequence[SurvivalRow],
    flows: Sequence[FlowRow],
    countries: dict[str, str],
    insights_html: str,
) -> str:
    survival_body = "".join(
        f"<tr{_attrs(source=source, country=countries.get(scope_id))}>"
        f"<td>{escape(LIFECYCLE_LABELS.get(status, status))}"
        f"{' <small>(right-censored)</small>' if censored else ''}"
        f"{' <small>(suppressed group)</small>' if postings is None else ''}</td>"
        f"<td>{escape(scope_id)}</td>"
        f'<td class="count{_suppressed_class(postings)}">{_count(postings)}</td>'
        f'<td class="count{_suppressed_class(postings)}">{_count(vacancies)}</td>'
        f'<td class="count{_suppressed_class(postings)}">{_stat(median)}</td>'
        f'<td class="count{_suppressed_class(postings)}">'
        f"{'—' if p25 is None and p75 is None else f'{_stat(p25)}–{_stat(p75)}'}</td>"
        f'<td class="count{_suppressed_class(postings)}">{_stat(max_days)}</td></tr>'
        for scope_id, status, censored, postings, vacancies, median, p25, p75, max_days, source in survival
    )
    flows_body = "".join(
        f"<tr{_attrs(bucket=f'{bucket_start:%Y-%m-%d}', source=source, country=countries.get(scope_id))}>"
        f"<td>{escape(scope_id)}</td><td>{escape(GRAIN_LABELS.get(grain, grain))}</td>"
        f"<td>{bucket_start:%Y-%m-%d}</td>"
        f'<td class="count{_suppressed_class(openings)}">{_count(openings)}</td>'
        f'<td class="count{_suppressed_class(closures)}">{_count(closures)}</td>'
        f'<td class="count{_suppressed_class(active_postings)}">{_count(active_postings)}</td>'
        f'<td class="count{_suppressed_class(active_vacancies)}">{_count(active_vacancies)}</td></tr>'
        for scope_id, grain, bucket_start, openings, closures, active_postings, active_vacancies, source in flows
    )
    charts = "".join(
        _sparkline(
            _active_series(series, grain),
            f"{GRAIN_LABELS.get(grain, grain)} active postings within one source scope: {scope_id}",
        )
        for scope_id in sorted({row[0] for row in flows})
        # ponytail: finest grain per scope; coarser grains stay in the table below.
        for grain, series in (_finest_series([row for row in flows if row[0] == scope_id]),)
        if series
    )
    return (
        insights_html
        + _definition(
            "A posting leaving the source is reported as posting duration or inferred removal, "
            "never as time to hire: the observatory cannot see hiring outcomes. Active postings are "
            "right-censored lower bounds, not completed durations. Advertised vacancies are counted "
            f"separately from postings. In this table and the flow table below, groups of 1 to "
            f"{SUPPRESSION_THRESHOLD - 1} postings are suppressed rather than shown, together with "
            "the vacancy and duration figures of that group; a true zero posting count stays visible."
        )
        + _table(
            "Posting survival by closure basis. Advertised vacancies are counted separately from postings.",
            (
                ("Basis", False),
                ("Scope", False),
                ("Postings", True),
                ("Advertised vacancies", True),
                ("Median days", True),
                ("P25–P75 days", True),
                ("Max days", True),
            ),
            survival_body,
            name="survival-basis",
            empty="No survival results",
        )
        + "<h3>Posting flows over time</h3>"
        + _definition(
            "Openings are postings first seen in the bucket, closures are postings last seen before "
            "it, and active postings are the stock still open. The line breaks wherever a bucket is "
            "suppressed or was never observed; a gap is never plotted as zero. Trends are read "
            "within one source and scope."
        )
        + charts
        + _table(
            "Posting openings, active stock, and closures over time (daily, weekly, monthly)",
            (
                ("Scope", False),
                ("Period", False),
                ("Bucket", False),
                ("Openings", True),
                ("Closures", True),
                ("Active postings", True),
                ("Active vacancies", True),
            ),
            flows_body,
            name="survival-flows",
            empty="No trend results",
        )
    )


def _render_quality(
    coverage: Sequence[CoverageRow],
    frequency: Sequence[FrequencyRow],
    mapping_by_scope: Mapping[ScopeKey, Sequence[MappingRow]],
    countries: dict[str, str],
    scopes: Sequence[ScopeKey],
) -> str:
    coverage_body = "".join(
        f"<tr{_attrs(country=country, source=source)}>"
        f"<td>{escape(source)}</td><td>{escape(scope_id)}</td><td>{escape(country or '—')}</td>"
        f"<td>{_time(observed_at)}</td>"
        f'<td class="count">{expected_rows:,}</td><td class="count">{observed_rows:,}</td>'
        f'<td class="count">{_stat(age_hours)}</td>'
        f"<td>{_badge(freshness_status, coverage_status)}</td>"
        f'<td class="wrap">{escape(limitations or "—")}</td></tr>'
        for (
            source,
            scope_id,
            country,
            observed_at,
            expected_rows,
            observed_rows,
            freshness_status,
            coverage_status,
            age_hours,
            limitations,
            _threshold_hours,
        ) in coverage
    )
    frequency_body = "".join(
        f"<tr{_attrs(source=source, country=countries.get(scope_id))}>"
        f'<td>{escape(source)}</td><td>{escape(scope_id)}</td><td class="count">{sweeps:,}</td>'
        f"<td>{first:%Y-%m-%d} to {last:%Y-%m-%d}</td>"
        f'<td class="count">{_stat(interval)}</td>'
        f'<td class="count">{threshold if threshold is not None else "—"}</td>'
        f'<td class="wrap">{escape(limitations or "—")}</td></tr>'
        for scope_id, sweeps, first, last, interval, threshold, limitations, source in frequency
    )
    missing_blocks: list[str] = []
    for source, scope_id in scopes:
        missing_body = "".join(
            f"<tr{_attrs()}><td>{escape(dimension)}</td><td>{escape(status)}</td>"
            f'<td class="count">{count:,}</td></tr>'
            for dimension, status, count in mapping_by_scope.get((source, scope_id), [])
            if status != "mapped"
        )
        missing_blocks.append(
            f"<h4>{escape(_scope_label(source, scope_id))}</h4>"
            + _table(
                "Mapping outcomes that are not mapped",
                (("Dimension", False), ("Status", False), ("Outcomes", True)),
                missing_body,
                name=f"quality-missing-{_scope_slug(source, scope_id)}",
                empty="No missing mapping results",
            )
        )
    return (
        _definition(
            "Coverage is deterministic: expected rows come from the sweep manifest and observed rows "
            "from the stored partition, so a shortfall is reported as partial coverage rather than "
            "silently absorbed. A stale scope is still published, clearly labelled, instead of hidden."
        )
        + _table(
            "Source coverage and freshness for the latest complete sweeps",
            (
                ("Source", False),
                ("Scope", False),
                ("Country", False),
                ("Observed", False),
                ("Expected rows", True),
                ("Observed rows", True),
                ("Age (h)", True),
                ("Status", False),
                ("Known limitations", False),
            ),
            coverage_body,
            name="quality-coverage",
            empty="No coverage results",
        )
        + "<h3>Collection frequency</h3>"
        + _definition(
            "Collection cadence per scope. A median interval longer than the freshness threshold "
            "means trend buckets can be sparse; sparse buckets are shown as gaps, not as zeros."
        )
        + _table(
            "Source coverage and collection frequency, published beside the metrics.",
            (
                ("Source", False),
                ("Scope", False),
                ("Complete sweeps", True),
                ("Observed span", False),
                ("Median interval (h)", True),
                ("Freshness threshold (h)", True),
                ("Known comparability limitations", False),
            ),
            frequency_body,
            name="quality-frequency",
            empty="No coverage results",
        )
        + "<h3>Missing and uncertain mappings</h3>"
        + _definition(
            "Outcomes that are not mapped are published so that missing reference data is visible. "
            "These postings are excluded from mapped demand and are not redistributed. Each table "
            "belongs to one collecting scope; scopes are never summed."
        )
        + "".join(missing_blocks)
    )


def _render_methodology(provenance: Sequence[ProvenanceRow]) -> str:
    definitions = (
        (
            "Openings",
            "Postings first observed in a bucket, based on first_seen = min(observed_at).",
        ),
        ("Closures", "Postings last observed before a bucket and absent afterwards."),
        ("Active postings", "Postings observed as open in the sweep covering the bucket."),
        (
            "Advertised vacancies",
            "Vacancy counts advertised inside postings, counted separately from postings.",
        ),
        (
            "Posting duration",
            "Observed days between first and last sighting; for open postings it is a "
            "right-censored lower bound. It is never time to hire.",
        ),
        ("Freshness", "Observation age against the source freshness threshold."),
        ("Coverage", "Observed rows against expected rows for the same sweep."),
        (
            "Suppression",
            f"In the posting-flow and survival tables, groups of 1 to {SUPPRESSION_THRESHOLD - 1} "
            "postings are suppressed to avoid singling out an individual posting, and the vacancy "
            "and duration figures of a suppressed group are masked with it. A true zero posting "
            "count stays visible, and latest-sweep counts by country, region, occupation, skill, "
            "employment type, working hours, and contract duration are published in full.",
        ),
    )
    body = "".join(
        f"<tr{_attrs(source=source)}><td>{escape(source)}</td><td>{escape(scope_id)}</td>"
        f'<td>{_time(observed_at)}</td><td class="count">{row_count:,}</td>'
        f"<td>{escape(source_version or '—')}</td><td>{escape(nuts_version or '—')}</td>"
        f"<td>{escape(taxonomy_version or '—')}</td><td>{escape(esco_version or '—')}</td>"
        f"<td>{_licence(licence_reference)}"
        f"<br><small>{escape(access_method or '—')}</small></td></tr>"
        for (
            source,
            scope_id,
            observed_at,
            licence_reference,
            access_method,
            source_version,
            nuts_version,
            taxonomy_version,
            esco_version,
            row_count,
        ) in provenance
    )
    terms = "".join(f"<dt>{escape(term)}</dt><dd>{escape(text)}</dd>" for term, text in definitions)
    return (
        _definition(
            "Every metric on this page is an aggregate of public job-vacancy postings. Native "
            "posting identifiers, source URLs, and free text are removed at the privacy boundary "
            "before anything is stored for publication."
        )
        + f'<dl class="definitions">{terms}</dl>'
        + "<h3>Provenance and licences</h3>"
        + _definition(
            "The latest valid complete sweep per source and scope, with the licence, access method, "
            "and pinned reference versions used to produce it. Use the CSV control to download this "
            "metadata table."
        )
        + _table(
            "Latest complete sweep provenance, licences, and pinned reference versions",
            (
                ("Source", False),
                ("Scope", False),
                ("Observed", False),
                ("Rows", True),
                ("Source version", False),
                ("NUTS", False),
                ("JobTech taxonomy", False),
                ("ESCO", False),
                ("Licence", False),
            ),
            body,
            name="methodology-provenance",
            empty="No provenance results",
        )
    )


def _render_governance(provenance: Sequence[ProvenanceRow]) -> str:
    """Licences, retention, privacy assessment, architecture, and the reproducible snapshot."""
    # ponytail: one row per source, taken from its most recently observed scope, so this table
    # cannot disagree with the per-scope provenance table in the methodology section.
    newest: dict[str, ProvenanceRow] = {}
    for row in provenance:
        held = newest.get(row[0])
        if held is None or row[2] > held[2]:
            newest[row[0]] = row
    body = "".join(
        f"<tr{_attrs(source=source)}><td>{escape(source)}</td><td>{_licence(row[3])}</td>"
        f"<td>{escape(row[4] or '—')}</td><td>{escape(row[5] or '—')}</td>"
        f'<td class="wrap">{escape(terms[0])}</td><td class="wrap">{escape(terms[1])}</td></tr>'
        for source, row in sorted(newest.items())
        for terms in (SOURCE_TERMS.get(source, DEFAULT_TERMS),)
    )
    retention = "".join(
        f"<dt>{escape(term)}</dt><dd>{escape(text)}</dd>" for term, text in RETENTION
    )
    privacy = "".join(f"<li>{escape(text)}</li>" for text in PRIVACY)
    steps = "".join(
        f"<dt>{escape(step)}</dt><dd>{escape(text)}</dd>" for step, text in ARCHITECTURE
    )
    return (
        '<p class="lede">Where the data comes from, what is kept, what is deliberately not '
        "published, and how to rebuild this page from scratch.</p>"
        + "<h3>Source licences and reuse</h3>"
        + _definition(
            "One row per source, read from the licence reference of that source's most recently "
            "observed complete sweep; the methodology section lists every scope separately. "
            "Aggregates on this page may be reused with attribution; posting text and native "
            "identifiers are not published and are not available here."
        )
        + _table(
            "Source licences, access methods, attribution requirements, and raw-data retention",
            (
                ("Source", False),
                ("Licence", False),
                ("Access", False),
                ("Source version", False),
                ("Attribution and reuse", False),
                ("Raw data retention", False),
            ),
            body,
            name="governance-licences",
            empty="No licence results",
        )
        + "<h3>Retention</h3>"
        + f'<dl class="definitions">{retention}</dl>'
        + "<h3>Privacy assessment</h3>"
        + f'<ul class="workflow">{privacy}</ul>'
        + "<h3>Small-count disclosure control</h3>"
        + _definition(
            f"Groups of 1 to {SUPPRESSION_THRESHOLD - 1} postings are masked in the posting-flow "
            "and survival views only, and a true zero in the posting counts those views key on "
            "always stays visible. Vacancy and duration figures are masked together with the group "
            "they describe, so they read as suppressed or as a dash whenever their posting count "
            "does. No other view on this page is suppressed: latest-sweep counts by country, "
            "region, occupation, skill, employment type, working hours, and contract duration are "
            "published exactly as observed, and each of those tables is a single-dimension "
            "distribution, never a cross-tabulation."
        )
        + "<h3>Architecture overview</h3>"
        + f'<dl class="definitions">{steps}</dl>'
        + "<h3>Reproducible demonstration snapshot</h3>"
        + _definition(
            f"This page is {_build_basis()}. The synthetic sample is committed to the repository "
            "and regenerated with `uv run --offline python -m scripts.probe --sample`, and `make "
            "site` rebuilds this page from it with no network access, so the build stays reviewable "
            "if a live source becomes unavailable. Offline builds are labelled as synthetic here "
            "rather than presented as observations of a real market."
        )
        + "<h3>Methodology version</h3>"
        + _definition(
            "How each scope's data was drawn: the `ba / de-nuts3-panel` scope is a stratified "
            "region-bounded sample with a capped within-stratum draw over a frozen 400-region "
            "NUTS-3 panel - not a census and not a partial crawl - so its counts describe the "
            "sample, and the caveat printed beside them is the panel's own limitation string "
            "from the sweep manifest. The `jobtech` keyword scope is a keyword-scoped query over "
            "all current Swedish postings matching a fixed query, not a sample. One published "
            "scope (the German panel) carries no structured occupation field, which is why its "
            "occupation and skill rankings are empty by construction rather than through a "
            "mapping failure; no job title or free text is ever classified to fill them."
        )
        + _definition(
            f"Methodology version {METHODOLOGY_VERSION}, covering the definitions, mapping rules, "
            "and suppression rule described on this page. The version and build time are printed in "
            "the footer, and every CSV downloaded from this page carries the version in its "
            "file name."
        )
    )


def build_site(database: Path, target: Path) -> int:
    connection = duckdb.connect(str(database), read_only=True)
    try:
        demand = _query_demand(connection)
        coverage = _query_coverage(connection)
        region_breadth = _query_region_breadth(connection)
        regions = _query_dimension(connection, region=True)
        occupations = _query_dimension(connection, region=False)
        skills = _query_skills(connection)
        mapping = _query_mapping(connection)
        mapping_coverage = _query_mapping_coverage(connection)
        requirements = _query_requirements(connection)
        flows = _query_flows(connection)
        survival = _query_survival(connection)
        frequency = _query_frequency(connection)
        provenance = _query_provenance(connection)
    finally:
        connection.close()
    # One subsection per (source, scope_id), largest first: no ranking, denominator or table is
    # ever shared between scopes, so nothing on the page pools them.
    scopes = _scope_keys(demand)
    regions_by_scope = _group_dimensions(regions)
    occupations_by_scope = _group_dimensions(occupations)
    skills_by_scope = _group_dimensions(skills)
    mapping_by_scope = _group_mapping(mapping)
    requirements_by_scope = _group_requirements(requirements)
    # Scope-keyed views carry no country column, so the filter bar needs this crosswalk to make
    # the country selector apply to the survival, flow, and frequency rows too.
    countries = {row[1]: row[2] for row in demand if row[2]}
    countries.update({row[1]: row[2] for row in coverage if row[2]})
    # The breadth line's caveat is the manifest's own string, rendered verbatim, so the page and
    # the manifest cannot drift. Coverage index 9 is coverage_limitations.
    limitations: dict[ScopeKey, str | None] = {(row[0], row[1]): row[9] for row in coverage}
    breadth_by_scope = {(row[0], row[1]): row for row in region_breadth}
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
    scope_labels = {row[1]: _scope_label(row[0], row[1]) for row in demand}
    digest = _insight_groups(
        _insights_by_scope(
            [
                insight
                for slug, _heading in SECTIONS
                for insight in insights_by_section.get(slug, [])
            ]
        ),
        scope_labels,
    )
    built = datetime.now(UTC)
    rendered = {
        "overview": _render_overview(demand, coverage, flows, frequency, breadth_by_scope, digest),
        "status": _render_status(
            coverage,
            frequency,
            built,
            _insight_groups(
                _insights_by_scope(insights_by_section.get("status", [])), scope_labels
            ),
        ),
        "countries": _render_countries(
            demand,
            regions_by_scope,
            mapping_coverage,
            scopes,
            countries,
            breadth_by_scope,
            limitations,
            _insights_by_scope(insights_by_section.get("countries", [])),
            coverage,
        ),
        "occupations": _render_occupations(
            occupations_by_scope,
            skills_by_scope,
            mapping_by_scope,
            mapping_coverage,
            scopes,
            _insights_by_scope(insights_by_section.get("occupations", [])),
            countries,
        ),
        "requirements": _render_requirements(
            requirements_by_scope,
            scopes,
            _insights_by_scope(insights_by_section.get("requirements", [])),
            countries,
            demand,
        ),
        "survival": _render_survival(
            survival,
            flows,
            countries,
            _insight_groups(
                _insights_by_scope(insights_by_section.get("survival", [])), scope_labels
            ),
        ),
        "quality": _render_quality(coverage, frequency, mapping_by_scope, countries, scopes),
        "methodology": _render_methodology(provenance),
        "governance": _render_governance(provenance),
    }
    links: list[str] = []
    for index, (slug, heading) in enumerate(SECTIONS):
        current = ' aria-current="page"' if index == 0 else ""
        links.append(f'<a href="#{slug}" data-tab="{slug}"{current}>{escape(heading)}</a>')
    nav = "".join(links)
    sections = "".join(_panel(slug, heading, rendered[slug]) for slug, heading in SECTIONS)
    filters = _render_filters(
        demand,
        [row for rows in occupations_by_scope.values() for row in rows],
        [row for rows in skills_by_scope.values() for row in rows],
    )
    updated = max((row[3] for row in demand), default=None)
    stamp = (
        f"Last successful update {_time(updated)}. " if updated else "No successful update yet. "
    )
    summary = (
        f"{stamp}{len(demand)} independently sourced country observation(s). "
        "Counts are not summed or deduplicated across sources."
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"""<!doctype html>
<html lang="en" data-methodology-version="{escape(METHODOLOGY_VERSION, quote=True)}" data-built="{built.isoformat()}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#f4f6f5">
  <meta name="description" content="Aggregate European technology job-posting demand, posting duration, source coverage, and provenance.">
  <link rel="icon" href="data:,">
  <title>EU Tech Labour Observatory</title>
  <style>{STYLE}  </style>
</head>
<body>
  <a class="skip" href="#main">Skip to main content</a>
  <header><div>
    <h1>EU Tech Labour Observatory</h1>
    <p>Where technology postings are advertised, which skills they ask for, and how long they stay up.</p>
    <p><small>{summary}</small></p>
  </div></header>
  <nav class="tabs-outer" aria-label="Sections"><div class="tabs">{nav}</div></nav>
  <main id="main" tabindex="-1">
    {filters}
    {sections}
    <footer>Aggregate observations only. Native posting identifiers and private text are not published. Figures describe observed postings, not hiring outcomes, and are not real time.
    <br>Methodology version {escape(METHODOLOGY_VERSION)} · page {_time(built)} · {escape(_build_basis())}. Reuse the aggregates with attribution to each source; see Governance.</footer>
  </main>
  <script>{SCRIPT}</script>
</body>
</html>
""",
        encoding="utf-8",
    )
    return len(demand)


def main() -> int:
    count = build_site(DATABASE, TARGET)
    print(f"wrote {TARGET.relative_to(ROOT)} ({count} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
