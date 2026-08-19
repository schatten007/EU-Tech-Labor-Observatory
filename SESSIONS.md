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
| 11 | 2026-08-17 | Dashboard scope complete; user validation pending | Add the operations-facing dashboard scope of Iteration 11: Status run summary, Governance (licences, retention, privacy assessment, disclosure control, architecture, snapshot), a versioned methodology stamp, and an offline release-check gate over the built page. | `make check && make release-check` passed |
| 11a | 2026-08-19 | Complete | First real collection: fix the collector's country assumption against the live JobTech payload, filter the sweep to Sweden at the source, and scope sample-only dbt tests out of `live-site`. | `make check && make sweep && make live-site` passed |


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

### 2026-08-17 - Iteration 11

- Split Iteration 11 by surface: this session did only the dashboard-facing half (Status,
  Governance, release checks). Scheduling, alert delivery, backups, backfills, and schema
  migrations are untouched and stay open.
- New `Status` section is the operational run summary: latest complete sweep, fresh and covered
  scope counts, sweeps published, build stamp, and one plain sentence per scope stating age
  against the freshness threshold and stored versus expected rows. It also states that failed or
  partial runs never enter the warehouse, so absence and ageing are the only failure signals.
- New `Governance` section publishes per-source licence and attribution (deduplicated from
  `latest_complete_sweeps`), retention rules, a four-point privacy assessment that names the
  residual small-cell risk in the latest-sweep marts, the k=5 rule restricted to the two masked
  views, the five-step architecture, and the reproducible-snapshot statement. `_build_basis()`
  reads `OBSERVATIONS_PATH`, so a sample build is labelled synthetic on the page.
- `METHODOLOGY_VERSION = "1.0"` is stamped in the footer, on `<html data-methodology-version>`,
  and appended to every CSV filename by the inline script. `data-filtered-empty` moved from the
  cell to its `<tr>` so the only `hidden` attributes in the served HTML are progressive-enhancement
  hooks; `_licence()` renders a dash instead of an empty `href` when a licence reference is null.
- `scripts/release_check.py` (stdlib + `html.parser`) checks the built page for accessibility
  (lang, one h1, heading order, captions, `th scope`, labels, chart `aria-label`, duplicate ids),
  links and assets (internal anchors resolve, no external asset, external URLs against a string
  allowlist that is never fetched), disclosure (no 1..k-1 count cell in `table-survival-basis` or
  `table-survival-flows`, no key-like token or email, prose k matches the macro), and no-JS
  readability. `make release-check` runs it after `make site`; it is not in `make check`.
- Gotcha for the next session: the publish fixture writes `posting_flows` directly, so its small
  counts bypass the dbt mask; the test asserts the checker flags exactly those and nothing else.
  The usability study (>=5 students or recent graduates; tasks: technology demand in one region,
  two occupations within one source, a skill comparison, what a removed posting means, whether DE
  and SE numbers are comparable) has not run, and no interface revision has been made from it.
- Post-review corrections, all pinned by tests: the Status prose now matches
  `source_coverage.sql` instead of overstating it - only *complete* manifests are loaded (approval
  and row-count problems are labelled, and only `labour_demand_latest` filters on `covered`),
  Partial coverage covers shortfall, surplus, and wrong-country rows, and Unknown coverage is
  named as unapproved or incomplete metadata. `_run_state` branches on the real arithmetic instead
  of always saying "incomplete", `_query_coverage` selects `freshness_threshold_hours` so the
  quoted threshold is the one that set the badge (not `collection_frequency`'s history-wide
  `max`), the run-summary row count comes from `observed_rows` rather than the manifest's
  `row_count`, the governance licence row is the source's newest sweep rather than its first
  scope, and the k=5 claim now says a true zero *posting count* stays visible because vacancy and
  duration figures are masked with their group. In `release_check.py`: a `<label>` without `for`
  no longer vouches for every id-less control, a missing masked view or count column is itself a
  failure (so a rename cannot silently disable the disclosure rule), a figure published beside a
  suppressed keying count is flagged, asset detection covers any fetching attribute, and the
  secret/email scans are case-insensitive and cover attribute values. Publish tests now pin
  `OBSERVATIONS_PATH` for both build-basis labels instead of depending on the ambient value.


### 2026-08-19 - Iteration 11a

- The first real sweep failed on its first hit. Live JobTech omits top-level `country_code` and
  nests SCB code `199` (Sverige) in `workplace_address`, but the collector demanded ISO `SE`.
  Only the synthetic fixture ever used `SE`, so the offline gate could never have caught this;
  the normaliser now accepts both codes and still stores `SE`.
- Platsbanken answers a Swedish keyword with a few genuinely foreign ads (1 Frankrike, 1 Danmark
  out of 622). Sweden-only is an approval constraint, so the sweep now sends `country=199` and
  lets the API exclude them. Dropping them locally instead would have broken the one-row-per-hit
  and `row_count`/`total` reconciliation invariants, and would have reported partial coverage
  forever. The scope id changed with the new parameter, which is correct: it is a different scope.
- `make live-site` had never been run against live data and could not have succeeded. `dbt
  build` ran four tests that assert facts about the synthetic sample (its zero-row sweep, its
  stale scope, its exact closure timeline). They are tagged `sample_fixture` and excluded there;
  `assert_source_coverage` was split so the real coverage and freshness invariants still run on
  live partitions.
- `assert_survival_logic` passed on the first live sweep only because both sides of the set
  comparison were empty. It would have failed on the second sweep, once inferred closures existed.
- Changing the scope params and the limitations text invalidated the generated sample, which is
  built from the same two values, so `make sample` was re-run: without it `make site` would have
  published a limitation sentence the collector can no longer produce. `assert_key_rotation_does_
  not_close` turned out to be sample-pinned too (it matches one fixture timestamp), so it is tagged
  and its live-safe half now exists as `assert_no_cross_key_closures`, which pins no date.
- The page request is now derived from the recorded scope (`_search_params`) instead of a second
  literal, because a manifest claiming "filtered to Sweden" must not be able to outlive the filter.
  A test asserts the filter on the captured URL; verified it fails when the parameter is dropped.
- First live partition: 620 rows over 7 pages, 620/620 rows covered, fresh at 0.06 h, and
  `release_check` clean on the live page. `make check` stays green on the sample at 36 Python
  tests and 163 dbt resources; `make live-site` runs 158 of them.

