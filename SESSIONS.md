# Implementation Sessions

Each increment is completed in one session. Keep unfinished work in the next row rather
than expanding the active increment.

| Increment | Session | Status | Scope | Check |
| --- | --- | --- | --- | --- |
| 1 | 2026-08-13 | Complete | Review the Phase 0 scaffold and establish a passing offline baseline. | `make check` passed |
| P1 | 2026-08-13 | Complete | Isolate raw responses and add the minimum PII sanitization boundary. | `make sample && make check` passed |
| 2 | 2026-08-13 | Complete | Add the smallest raw observation collector against ignored private responses. | Offline collector check passed |
| 3 | 2026-08-13 | Complete | Point staging at collected observations while preserving its contract. | `make sample && make check` passed |
| 4 | 2026-08-13 | Complete | Derive posting presence and closure events. | `make sample && make check` passed |
| 5 | 2026-08-13 | Complete | Publish one minimal labour-demand view. | `make site` passed |
| 6 | 2026-08-15 | Complete | Add reliable, resumable, immutable JobTech query sweeps. | `make sample && make check && make site` passed |
| 7 | 2026-08-15 | Complete at feasibility boundary | Review DE/SE sources; add approved-source metadata, coverage, and freshness without unsupported German collection. | `make sample && make check && make site` passed |
| 8 | 2026-08-16 | Complete | Add region, occupation, and skill mappings from real pinned crosswalks with quality reporting. | `make reference && make sample && make check && make site` passed |
| 9 | 2026-08-17 | Complete | Add historical analytics: openings, active stock, and closures over time (day/week/month); posting survival and closure basis; postings vs advertised vacancies; small-count suppression; coverage and collection frequency. | `make sample && make check && make site` passed |
| 10 | 2026-08-17 | Complete | Publish an accessible six-section dashboard: persistent filters with shareable hash URLs, server-rendered SVG trend charts, metric definitions, explicit empty/stale/partial-coverage/error states, and per-table CSV export. | `make check && make site` passed |

## Session Notes

### 2026-08-13 - Increment 1

- Reviewed all source, configuration, schema, and SQL files without opening datasets or
  fixtures.
- Kept this increment to baseline correctness; no collector or dashboard scaffolding.
- Fixed formatting, test collection, dbt CLI argument order, repository-relative DuckDB
  paths, staging timestamp type, and enforceable key null checks.
- Added one small check proving the default probe command does not access the network.
- Enforced offline dependency resolution for every command in `make check`.
- Rebuilt the committed sample offline because its existing schema predated the sample
  builder's explicit projection.
- Final result: `make check` passed with one Python test and six dbt resources passing.

### 2026-08-13 - Privacy Increment P1

- Added `scripts/sanitize.py` as the only privacy boundary: normalized NDJSON enters,
  allowlisted analytical NDJSON leaves.
- Pseudonymized source IDs with HMAC-SHA256 and a required 32-character
  `OBSERVATORY_HMAC_KEY`; stable IDs preserve longitudinal joins without publishing
  native identifiers.
- Kept dates, coarse geography, occupation, language, skill URIs, and vacancy counts.
  Dropped all unspecified fields, including title, description, employer, contacts,
  organization number, URL, city, and postcode.
- Moved future live probe responses from tracked fixtures to ignored `data/raw/probe/`
  and removed the four committed live-response fixtures.
- Replaced the sample builder's fixture dependency with two synthetic rows and removed
  title, employer, and text from the staging contract.
- Deliberate boundary: skill extraction from private text must happen before sanitizing;
  only normalized skill URIs cross into analytical data.
- Final result: `make sample && make check` passed with two Python tests and six dbt
  resources passing.

### 2026-08-13 - Increment 2

- Added the offline JobTech collector for recorded raw responses.
- Normalized source dates, country, language, vacancy count, and observation time.
- Applied the existing sanitizer before writing NDJSON, so native IDs and private fields
  never leave the collector boundary.
- Final result: `make check` passed with three Python tests and six dbt resources
  passing.

### 2026-08-13 - Increment 3

- Replaced the source-native Parquet sample with sanitized observation NDJSON generated
  through the same normalization and privacy boundary as collected responses.
- Pointed staging at `OBSERVATIONS_PATH`, with the committed synthetic sample as its
  offline default.
- Preserved the ten-column staging contract and observation grain; staging now only
  selects and casts collector fields.
- Standardized script commands on `python -m scripts...` so package imports work without
  path manipulation.
- Final result: `make sample && make check` passed with three Python tests and six dbt
  resources passing.

### 2026-08-13 - Increment 4

- Added one event view: each observation becomes a presence event and each posting may
  produce one closure event.
- Preferred source-reported `removed_at`; otherwise inferred closure at the first later
  complete source sweep where the posting is absent.
- Expanded the synthetic sample to cover persistence, reported closure, and inferred
  closure, with one exact-set survival test.
- Deliberate ceiling: each `(source, observed_at)` is a complete, consistently scoped
  sweep. Partial or partitioned collection needs a scope key before feeding this model.
- Final result: `make sample && make check` passed with three Python tests and eight dbt
  resources passing.

### 2026-08-13 - Increment 5

- Added one aggregate model: active postings by source and country at each source's
  latest complete sweep.
- Added a self-contained static HTML publisher using Python, DuckDB, and the standard
  library; no frontend framework, runtime JavaScript, external assets, or new dependency.
- Published only counts, source, country, and observation time. Native IDs and private
  posting text do not enter the aggregate or page.
- Added one offline publisher test and checked the built page at desktop and mobile
  widths with no page overflow, text overlap, or external requests.
- Final result: `make check && make site` passed with four Python tests and nine dbt
  resources passing.

### 2026-08-15 - Iteration 6

- Added serial JobTech pagination with a canonical query scope, bounded transient retries,
  `Retry-After` support, durable page checkpoints, and resumable collection state.
- Added immutable timestamped partitions, atomic publication, content hashes, run locks,
  exact-rerun idempotency, and explicit complete/failed sweep manifests.
- Added source/scope/sweep provenance to privacy-safe observations and publishable demand
  aggregates without allowing native identifiers or private source fields through.
- Gated staging, latest demand, and inferred closures on complete same-scope manifests;
  failed, partial, orphaned, and zero-row sweeps now have explicit tested behavior.
- Kept live collection opt-in through `make sweep` and preserved the network-free sample,
  quality gate, and static-site build.

### 2026-08-15 - Iteration 7

- Approved JobTech JobSearch for the fixed Swedish keyword scope based on its official API
  and CC0 publication; recorded source version, licence, access method, expected country,
  freshness threshold, and limitations in every new manifest.
- Rejected BA Jobsuche because BA terms prohibit automated collection, kept HR-BA-XML
  exploratory because it requires an agreement and does not document a national read feed,
  rejected EURES without formal partner access, and classified the official BA statistics
  API as aggregate-only.
- Did not implement or simulate German posting collection and did not label the product as
  Germany-Sweden complete.
- Added deterministic source coverage/freshness models, strict Swedish country validation,
  zero-row country coverage, and source-separated publication with no combined total.

### 2026-08-15 - Iteration 8

- Added deterministic pre-privacy enrichment from structured JobTech geography, occupation,
  and skill fields using pinned local reference tables and manual-review decisions.
- Added NUTS 2024 region, ESCO 1.2.1 occupation, and ESCO 1.2.1 skill demand views, plus
  separate quality outcomes for mapped, ambiguous, low-confidence, unmapped, and not-present
  values.
- Added a privacy-safe labelled review sample and deterministic precision/recall report.
- Kept Germany, text classification, trends, deduplication, and dashboard redesign out of
  scope.

### 2026-08-16 - Iteration 8 (reference hardening)

- Added `scripts/build_reference.py` (`make reference`, opt-in network) that regenerates the
  pinned crosswalks from the JobTech Taxonomy v30 GraphQL API, which returns ESCO 1.2.1 URIs
  directly. Committed the real output: 21 Swedish län to NUTS 2024, 3891 occupation mappings,
  19782 skill mappings, plus `reference_manifest.json` provenance.
- Replaced every placeholder ESCO URI with real taxonomy data; municipalities resolve to NUTS
  via their län-code prefix, giving complete Sweden coverage from 21 authored region rows.
- Repointed the synthetic sample at real developer-scope concept ids and made the latest
  main-scope sweep mapped, so the published page shows real region, occupation, and skill demand.
- Reframed the offline precision/recall report as a regression check against the official
  JobTech to ESCO crosswalk, not an independent accuracy audit, and made the publisher query the
  mapping models directly instead of hiding missing relations.
- Added fixture-based enrichment/evaluation tests plus reference-integrity, geography-coverage,
  honesty, and source-id-leak assertions.

### 2026-08-17 - Iteration 9 (historical analytics)

- Built published views over the existing append-only sweep history and event log:
  `posting_flows` (openings, active stock, and closures at daily/weekly/monthly grain),
  `posting_survival` with intermediate `events/posting_lifecycle` (per-posting duration,
  closure basis, right-censoring), and `collection_frequency` (cadence plus comparability
  limits published beside the metrics).
- Surfaced `number_of_vacancies` through staging and kept posting counts distinct from
  advertised vacancy counts; a data test asserts the two diverge.
- Added `transform/macros/suppress_small_counts.sql` (`small_count_threshold`, k=5) and reused
  it to mask non-zero cells below the threshold in every historical mart. Zero stays visible.
- Labelled disappearance as posting duration or inferred removal, never time to hire, and
  framed trends within-source only (no cross-source or cross-country absolute comparison).
- Active-posting durations are right-censored lower bounds, surfaced as `any_right_censored`.
- Extended the offline sample with a persistent active cohort (regenerated via `make sample`)
  so one cell clears suppression without changing the pinned closure timeline; added 5 singular
  dbt tests. `make check` passed (dbt PASS=161, 27 pytest).
- Added root `AGENTS.md` capturing the stable conventions so they are not re-derived each
  session. Dashboard redesign remains Iteration 10.

### 2026-08-17 - Iteration 10 (elegant dashboard UI/UX)

- Rebuilt `scripts/publish.py` from one monolithic f-string into `_query_*` / `_render_*` /
  `_table` / `_panel` helpers composed by `build_site`, which keeps its signature and its
  `labour_demand_latest` row-count return. Every value still passes through `escape()`.
- Added the two previously unused publish views: `source_coverage` (expected vs observed rows,
  freshness/coverage status) and `latest_complete_sweeps` (licence, access method, pinned NUTS /
  JobTech / ESCO versions), and split the merged occupation+skill query into ranked per-dimension
  queries (`DIMENSION_LIMIT = 25`).
- Six real `<section>` panels (Overview, Countries, Occupations and skills, Survival, Data
  quality, Methodology) with `<h2>` headings, a skip link, `scope="col"`, focusable
  `role="region"` table wrappers, `:focus-visible`, `prefers-reduced-motion`, and the system
  font stack replacing the `Inter` reference.
- Charts are server-rendered inline SVG with a fixed `viewBox="0 0 720 160"`, `role="img"`,
  `<title>`/`<desc>`, one chart per scope at its finest published grain; suppressed buckets break
  the polyline instead of being plotted as zero. Deviation from the plan: charts are per scope,
  not per grain, because one line per grain silently merged two scopes.
- Filters (date range, country, source, occupation, skill), section tabs, `location.hash` state,
  and per-table CSV export are inline-JS progressive enhancement over `data-row` / `data-*`
  attributes; all content and every explicit state (empty, filtered-empty, stale, partial
  coverage, loading, error) is server-rendered and visible without JavaScript.
- `make check` passed offline (dbt PASS=161, 27 pytest); publish tests gained the two new
  fixture tables plus assertions for the sections, filter bar, SVG, badges, and CSV controls.
- Post-review corrections, all pinned by tests: `_query_coverage` now takes the latest sweep per
  scope (`qualify row_number()`) with a deterministic tiebreaker, so the "latest complete sweeps"
  table stopped rendering the whole sweep history and the Overview stat counts scopes, not sweeps.
  `_sparkline` reports the real peak (0 no longer prints as 1) and `_active_series` steps the axis
  by bucket date, so an unobserved period breaks the line like a suppressed one. The overview
  trend now picks a scope that actually publishes flows instead of falling back to all scopes.
  The relative-volume bar is scaled per source, and the k=5 claim names the two masked views
  instead of appearing above unsuppressed counts. `posting_flows`/`posting_survival`/
  `collection_frequency` now select `source` (kept last in the row tuples) and carry
  `data-source`/`data-country` via a scope-to-country crosswalk, so the country and source
  filters no longer silently skip the scope-keyed tables.
