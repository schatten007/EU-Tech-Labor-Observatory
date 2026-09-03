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
| 12 | 2026-08-20 | Collector complete; second scope blocked by the source | Add occupation-field scopes beside the keyword scope, verify on the wire that the source actually applied the requested filter, and refuse a scope whose rows cannot all be reached. The Data/IT scope is refused: 2589 records against a 2100-record traversal window. | `make check && make sweep && make live-site && make release-check` passed |
| 13 | 2026-08-21 | Complete; live effect measured but not yet published | Accept a sole `exact-match` when the crosswalk offers several candidates, and publish the posting denominator beside every ranking. Measured on the latest sweep's retained raw pages: occupation `mapped` 65 to 510 of 615. The stored partitions are immutable, so the page shows it only after the next sweep. | `make check && make live-site && make release-check` passed |
| 13a | 2026-08-22 | Complete; rule audited, one concept vetoed, figures published | Audit the exact-match tiebreak over 100% of its live population (29 concepts): 24 `same`, 4 `narrower-or-broader`, 1 `wrong`. The `wrong` concept had no correct ESCO URI to redirect to, so a reviewed refusal was added to `manual_reviews.csv` and `load_references` was taught to honour one. Published from a fresh 627-row sweep: occupation `mapped` 65 of 615 to 519 of 627. | `make check && make sweep && make live-site && make release-check && make sample` passed |
| 14 | 2026-08-22 | Complete; three dimensions published, one taxonomy code still unobserved | Publish employment type, working-hours type, and contract duration from three structured fields that are 100% present, mapped through a new hand-written reference to English labels. Every posting lands in exactly one row per dimension, so each published column sums to the sweep's 628 postings and `Not stated` is a visible row rather than a caveat; a new untagged assertion pins that on live partitions. Methodology version bumped to 1.2. | `make check && make sweep && make live-site && make release-check && make sample` passed |
| 13b | 2026-08-23 | Complete; the tiebreak is scored, refusals counted, both readings published | Extend the review sample from 3 rows to 32 so it covers every concept the exact-match tiebreak decides in the published sweep - 13 occupation and 16 skill - each row recording whether its verdict was transcribed from 13a or re-judged here. `scripts/evaluate.py` scores a correct refusal as a true negative, keeps `precision`/`recall` textbook, and publishes strict and lenient figures for the five `narrower-or-broader` concepts side by side under a rule written down before the numbers. The collision census is reported and enforced nowhere. No sweep, no network, and no published figure moved. | `make check && make live-site && make release-check` passed |
| 16 | 2026-08-24 | Complete; findings published, trend gate silent | State the findings instead of making the reader derive them: a pure stdlib inference layer (`scripts/insights.py`) renders a digest on Overview and one line at the top of the Occupations, Requirements, Survival, and Status sections, every sentence built from the tables beneath it with its denominator stated and every numeric token proven - by test - to appear in the source rows. Methodology bumped to 1.3 before the first insight rendered. The trend gate was pre-registered at N=14 sweeps / M=7 days and stays silent on 8 sweeps and 3 daily buckets with a gap at 08-21, exactly as pre-registered. Three 13b review carry-overs closed. | `make check && make live-site && make release-check` passed |
| 20-25 | 2026-08-31 | Planning only; scope decision recorded, Increment 18 cancelled | Record the sister scraper lab's descope of German collection from a full census to a stratified region-bounded sample, and replan the observatory's publishing work as Increments 20-25: widen the live globs, per-scope/country sections, a German breadth line, German occupation mapping, methodology 1.3 to 1.4, and an optional live service. Four earlier planning assumptions corrected against the checkout (no map, no mapped-share ratio, suppression not regional, no exhaustiveness test). No code, no sweep, no data. | Not run — markdown planning documents only |
| 20 | 2026-09-01 | Complete; every stored source can now reach the page, and the next failure is the intended one | Widen the source segment of all three live globs at unchanged depth, so `make live-site` reads `data/raw/collections/*/*/*/` instead of `jobtech/*/*/`: the sweep count (`Makefile:29`) and the exported `OBSERVATIONS_PATH`/`MANIFESTS_PATH` (`Makefile:101-102`). Partition shape confirmed as `source/scope_id/sweep_id` before editing, so the segment count after `data/raw/collections/` is unchanged and the count is a depth check: 8 stored sweeps before, 8 after. `LIVE_READY` (`Makefile:30`) left byte-identical, so zero sweeps still fails the build instead of publishing an empty page. Makefile only — no collector, dbt, publisher, test or data change. | `make check && make live-site && make release-check` passed |


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
- `live-site` and `clean` were cmd.exe-only and broke when make was started from Git Bash, where
  recipes run under `/usr/bin/sh`. `if not exist ... (...)` is a syntax error there, and worse,
  `set "VAR=value" &&` sets positional parameters instead of exporting, so dbt would have read the
  synthetic sample while the footer claimed live partitions. The paths are now target-specific
  `export`s, the sweep guard is a make-level `$(error)`, the timestamp comes from python instead of
  powershell, and `clean` uses `shutil`. Verified identical results from PowerShell (cmd.exe) and
  Git Bash (sh). `clean` also never worked: it omitted `--project-dir transform`.
- Three sweeps in, the multi-sweep path is exercised for real: 14 `inferred_absence` closures,
  survival rows, and day/week/month flow buckets, with every sweep `covered`.

### 2026-08-20 - Iteration 12

- A scope is now a keyword *or* an occupation field, never both: `_selector` reduces the two
  selectors to one and `_search_params` stays the single source for the recorded scope and the
  wire. The keyword `scope_id` is byte-identical (`jobtech-f5cf1d409aa51fad`, pinned by a test) and
  `make sample` produced no diff, so the four stored keyword sweeps are not orphaned.
- Resume rehydrates whichever selector the saved scope carries. Defaulting to `q` would have
  restarted an occupation-field sweep under a different `scope_id` and failed its own checkpoint.
- The filter guard is a majority test, not equality, because the first version was wrong on live
  data. Measured with `occupation-field=apaJ_2ja_LuF`: page 0 was 100/100 in-field, page 2 was
  97/100 — the source counts adjacent occupations as part of the query (a `Säkerhetsingenjör`
  answers a Data/IT search). An ignored parameter looks nothing like that: the camelCase name
  returned all 40,649 Swedish ads, where Data/IT is 6%. So the sweep aborts below a simple
  majority, and the occupation-field `coverage_limitations` now says the scope is not pure.
- **The Data/IT scope cannot be collected and was not opened.** The search API answers any
  `offset > 2000` with HTTP 400 whatever the limit (`limit=1&offset=2099` is a 400), so one query
  reaches at most 2100 records; Data/IT + country=199 reports 2589. The first attempt collected 21
  pages and died at `offset=2100`. Publishing that prefix as complete would close the 489 unseen
  postings as `inferred_absence` on the next sweep and invent a duration for each, so
  `_verify_reachable` now refuses the sweep on its first page, before any page is written.
- Splitting the field is the open decision, not a detail: slices each need to be independently
  complete, and every slice is its own `scope_hash`, so "never sum across scopes" would forbid a
  Data/IT total unless disjointness is proven — and the 3% cross-field bleed above shows the
  source's own grouping is not clean. Search `stats=occupation-group` is a noisy top-N (5 values,
  a duplicated term, summing 2031 of 2589), so a group inventory has to come from the Taxonomy
  API. Largest group measured: `DJh5_yyF_hEM` at 1157, comfortably inside the window.
- `make check` green at 50 Python tests and 163 dbt resources (no dbt resource added, so the
  `USER_MANUAL.md` PASS count is unchanged); `make sweep` still lands in the keyword scope (628
  rows, 7 pages, fifth partition); `make live-site` runs 158 and `release_check` is clean.
- Review caught three holes in the new guards, all now closed with tests. The reachable window has
  to follow the page-size grid (`2000 // page_size * page_size + page_size`), because offsets only
  land on multiples of the page size and rounding up let a non-divisor size pass the check and die
  at offset 2010 with 67 pages already written. The filter majority test now skips pages shorter
  than `JOBTECH_FILTER_MIN_SAMPLE`, because a two-row final page with one adjacent hit is exactly
  the threshold and the resumable checkpoint would refuse the same page forever. And an
  occupation field is now shape-checked against the concept-id format before any request: a typo
  the API answers with zero hits would have published a complete empty partition under a new
  scope, which is the one case the filter guard cannot see and which append-only scopes make
  permanent.

### 2026-08-21 - Iteration 13

- `_mapping` no longer discards a concept just because the crosswalk offers more than one
  candidate: if exactly one of them is an `exact-match`, that one is selected as `mapped` under a
  distinct `method = exact_match_tiebreak`. Two or more exact matches are a real conflict and stay
  `ambiguous`. The method is separate from `crosswalk` so every such decision stays auditable, and
  the `mapping_method` vocabulary is now pinned by `accepted_values` (eight values) because an
  unpinned vocabulary cannot be audited and would swallow a typo.
- Reach of the rule in the pinned reference, counted: 277 of 2179 occupation concepts and 820 of
  5962 skill concepts have several candidates of which exactly one is exact. 152 occupation and 96
  skill concepts have two or more exact matches and are still refused.
- **`make live-site` cannot show the improvement, and re-running it never will.** Enrichment happens
  before the privacy boundary, so each immutable partition already carries its own
  `*_mapping_status`, and `sanitize.py`'s allowlist drops the JobTech concept id — re-enriching a
  stored partition is not merely undesirable, it is impossible. Live figures were therefore measured
  by re-enriching the latest sweep's retained private checkpoint pages
  (`data/raw/collection-state/<sweep>/pages/`), with the pre-change rule reimplemented alongside so
  both halves are counted over one identical input set. That reimplementation reproduces the
  published distribution exactly (615 postings, occupation 456/63/65/31, skill 108/76/33/558/3),
  which is what makes the comparison trustworthy.
- Measured on the latest sweep (615 postings): occupation `mapped` 65 to 510 and `ambiguous` 456 to
  11, with `low_confidence` 63 and `unmapped` 31 untouched. Skill mappings `mapped` 33 to 76 and
  `ambiguous` 108 to 65; postings with at least one mapped skill 25 to 47. **None of this is on the
  page yet.** The published page still reads 65 of 615 and will until the next sweep is collected.
- **This is a provenance change, not a validated accuracy gain.** 445 of 615 postings changing state
  on one rule is an eightfold jump measured against a review sample of three rows. A sole stated
  equivalence is a defensible selection rule and `exact_match_tiebreak` makes each instance
  traceable, but nothing here measures live precision. The honest follow-up is a manual spot-check
  of a handful of tiebroken occupations and skills; it is not something this increment did, and
  nothing on the page claims improved accuracy.
- New view `mapping_coverage_latest`: one row per source, scope, sweep and dimension carrying
  `postings_total`, `postings_with_source_value` and `postings_mapped`, all counted as distinct
  postings. `mapping_quality_latest` could not carry this: its skill rows come from
  `stg_skill_mappings`, so they count mappings, and a posting asking for five mapped skills would
  inflate its own denominator. The three live denominators now on the page: region 589 mapped of
  615 with 589 carrying source geography; occupation 65 of 615 with all 615 carrying a structured
  occupation, so that loss is entirely in mapping and not in source coverage; skill 25 of 615 with
  only 57 carrying a structured skill at all. The skill figure looks bad and is published as-is.
- `assert_mapping_coverage.sql` is deliberately untagged, so it runs against live partitions too. It
  pins the narrowing `mapped <= with_source_value <= total`, the one-row-per-dimension grain, and
  the agreement of `postings_total` with `mapping_quality_latest.total_outcomes` for region and
  occupation only — never for skill, whose quality grain is per mapping (615 against 778). The file
  says so, so nobody "fixes" the asymmetry.
- The build now refuses to publish once a second scope has postings, because `_query_dimension`,
  `_query_skills` and `_query_mapping` all read their views without a scope filter and would sum
  unrelated populations under a denominator naming one sweep. Green today with one collecting scope,
  and a zero-row scope publishes no coverage row to collide with. Exercised by a test rather than
  left as an assumption. This is the deferral mechanism for per-scope sections: it fires the moment
  Increment 12b's slicing decision lands.
- `release_check` now insists each ranked table is directly preceded by its `class="denominator"`
  sentence, and treats a missing ranked table as a fault of its own. The sentence is consumed by the
  first table that follows it, so two rankings cannot lean on one denominator. Counts only: a
  percentage would invite a coverage trend that a single sweep cannot support.
- The skill ranking needed one extra clause. Its rows count postings per skill, so the eight
  published rows sum to 33 while the denominator states 25 distinct mapped postings; without saying
  that, a reader would try to reconcile the two. The definition text now does.
- Nothing in the offline gate exercises the new rule on its own, so four fixture concepts were
  added (`occ-tiebreak`, `occ-two-exact`, `skill-tiebreak`, `skill-two-exact`) and all four are in
  the placeholder set that keeps them out of the committed reference. `make sample` produced no
  diff, as predicted: of the sample's four occupation concepts one is all `close-match`, one is
  resolved by manual review, and two were already single exact matches. The real review sample did
  not move either — its only unmapped skill has one `broad-match` candidate — so occupation
  precision/recall stay 1.0/1.0 and skill 1.0/0.75, unedited.
- `make check` green at 53 Python tests and 175 dbt resources (12 new: the view, its nine column
  tests, the pinned method vocabulary, and the coverage assertion); `make live-site` runs 170 and
  `release_check` is clean on the live page.
- Review caught the traceability hole: `METHODOLOGY_VERSION` is the declared mechanism for tracing a
  saved figure back to the rules that produced it, it is stamped in the footer, in
  `data-methodology-version`, and in every CSV file name, and its own text claims to cover the
  *mapping rules* — yet a mapping rule had changed under it. Two CSVs both named
  `...-methodology-1-0.csv` would have carried figures from two different rules. Bumped to **1.1**,
  and the selection rule is now stated in the occupations definition text (stated, not praised: the
  page still makes no accuracy claim). A test pins both, because a silent revert to 1.0 is exactly
  the failure this guards.
- Open item, deliberately not fixed: the single-scope guard has no override, and scopes are
  append-only, so the first successful second-scope sweep blocks every republish — including an
  urgent privacy fix — until per-scope sections land. Not reachable today: `make sweep-datait` is
  refused by `_verify_reachable` before it can open the scope. Whoever lands the slicing decision
  should either ship per-scope sections with it or add a narrow single-scope escape hatch.

### 2026-08-22 - Iteration 13a

- **The audit covered 100% of the rule's live population, not a sample of it.** The tiebreak reaches
  277 of 2179 occupation and 820 of 5962 skill concepts in the pinned reference, but only **13
  occupation** and **16 skill** concepts occur in the 615-posting sweep it was measured on. All 29
  were audited by descending live impact, covering 445 of 445 delta postings and 43 of 43 delta skill
  mappings. There was no "next 15 by impact" to fall back on, because there is no tail.
- Task 1 reproduced the published old-rule distribution exactly before anything else was believed:
  occupation 456/63/65/31 and skill 108/76/33/558/3 over 615 postings, re-enriched offline from the
  retained raw pages of `20260820T235159Z-f5cf1d409aa5`.
- Verdicts: **24 `same`, 4 `narrower-or-broader`, 1 `wrong`.** Impact is extremely concentrated -
  `fg7B_yov_smw` `Systemutvecklare/Programmerare` alone is 350 of the 445 delta postings (78.7%) and
  is `same`; nine of the 13 occupation concepts move exactly one posting each.
- The one `wrong`: **`9yMK_8ep_D1K` `IT-säkerhetstekniker` → `riskanalytiker, cybersäkerhet`**. Not a
  judgement call - the crosswalk declares that same ESCO URI an `exact-match` for
  `FHwx_yXu_FAd` `IT-säkerhetsanalytiker` as well, and the analyst is plainly the owner. A security
  technician implements controls; a cybersecurity risk analyst quantifies risk. 1 posting of 615.
- The four `narrower-or-broader`: `TU7g_mwa_VzB` `Testutvecklare` → `IKT-testanalytiker`,
  `XZaM_BRb_3mM` `Infrastrukturarkitekt` → `it-nätverksarkitekt`, `iXzD_6DF_sL4` `Brandväggar` →
  `installera och uppdatera brandvägg` (a knowledge concept mapped to an action, because ESCO offers
  no bare firewall concept), and `uvcb_DuX_NW8` `Tekniska beräkningar/MATLAB` → `MATLAB`. In all four
  the pick is the best candidate the reference contains; none was forced to `same` to flatter the
  rule. 9 further postings of 615.
- **Correction to a standing assumption: the crosswalk's `target_label` is Swedish, not English.**
  ESCO 1.2.1 was pulled in the Swedish locale (221 of a 400-label sample carry å/ä/ö), so the audit
  is a Swedish-to-Swedish comparison. Any future audit should not budget for translation.
- **The decision rule's 1-2-`wrong` branch could not be executed as written, for two factual
  reasons, and this was reported before acting rather than papered over.** There is no correct ESCO
  URI for an IT security technician anywhere in the reference - the only neighbours are
  `säkerhetstekniker för inbyggda system` (embedded-specific) and `it-säkerhetsansvarig` (a manager,
  already owned by two other source concepts) - so a redirect could only trade one wrong mapping for
  another. And `load_references` skipped every manual row whose `status != "mapped"`, so a reviewer
  could redirect but never refuse.
- **Remedy: the veto the previous session predicted would be needed.** `ManualReview` now carries a
  status and an optional candidate; a row naming no target refuses the mapping outright. The refusal
  still publishes `method = "manual_review"`, so the pinned eight-value `mapping_method` vocabulary
  did not grow and `assert_mapping_outputs.sql` was untouched. Two invariants came with it: a status
  the loader cannot express is now an **error** rather than a silent skip (a dropped review reads
  exactly like no review), and a refusing row that also names a target is rejected as two
  contradictory intentions. `occupation,9yMK_8ep_D1K,,,,ambiguous,,13a-audit,2026-08-22` is the first
  such row. Effect on the measured sweep: occupation `mapped` 510 → **509**, `ambiguous` 11 → **12**,
  `exact_match_tiebreak` 445 → **444**. Skill untouched.
- **A collision guard was measured as the alternative remedy and deliberately rejected.** Requiring
  the sole exact match to be the only source concept claiming that URI is a systematic test - the
  defect it detects affects **34 of 277** tiebroken occupation concepts (12.3%) and **102 of 820**
  skill concepts (12.4%), closely matching the 2-of-13 and 2-of-16 rates the audit saw live. But on
  this sweep it would have refused 5 live concepts of which only 1 is `wrong`: it also kills
  `Xnmr_kYS_YKY` `SQL, frågespråk` → `SQL` (the rival claimant is *SQLite*) and `xZLY_ZU5_E1q`
  `Elektronikkonstruktion` → `designa elektroniska system` (the rival is the near-synonym
  `Elektronikutveckling`), both judged `same`. Collisions arise as often from duplicated source
  concepts as from mis-assertions, so it is a good diagnostic and a bad rule. Recorded here so the
  measurement is not repeated: it is the obvious narrowing and it does not work.
- **The occupation ranking hit `DIMENSION_LIMIT = 25` for the first time, and the denominator stopped
  reconciling.** 519 mapped postings, but the visible 25 rows sum to 514. `release_check` reported
  zero problems, because its rule is that a ranked table has a denominator sentence, not that the
  two agree. `_denominator` now takes the listed rows for a one-row-per-posting ranking and publishes
  the shortfall: "Only the 25 most frequent occupations are listed below, accounting for 514 of those
  mapped postings; the rest sit in an unlisted tail." Counts only, no percentage. The clause appears
  only when it is true, and never on the skill ranking, whose column legitimately exceeds its
  denominator because a posting is counted in each of its skills' rows.
- Published from a fresh sweep `20260822T160021Z-f5cf1d409aa5`: **627 rows, 7 pages**, seventh
  partition, keyword scope. Denominators moved region 589 of 615 → 598 of 627, occupation **65 of 615
  → 519 of 627** (all 627 carry a structured occupation, so the remaining loss is entirely in
  mapping), skill 25 of 615 → **47 of 627** with only 60 carrying a structured skill. Occupation
  outcomes on the page: `mapped` 519, `unmapped` 34, `low_confidence` 62, `ambiguous` **12** - the
  vetoed concept is one of those 12. The ranked occupation table went from 18 rows to 25 (truncated),
  and its long tail of single-posting occupations is now the bulk of the distribution.
- `make sample` produced the diff Iteration 13 did not: `reference_hashes` is stamped into every
  manifest, so the new `manual_reviews.csv` rewrote all 5 rows of `data/sample/sweeps_sample.ndjson`.
  Correct, committed. `postings_sample.ndjson` did not move, and neither did the evaluation: none of
  the pinned concepts (`CZkP_hCz_KM8`, `71Ji_irM_rSJ`, `3vry_gaE_yfQ`, `jBKc_5Yx_Y6T`,
  `qfkh_ZRK_w4W`) is tiebroken at all, so occupation stays 1.0/1.0 and skill 1.0/0.75.
- `make check` green at **56 Python tests** (three added: the veto, its rejected-row invariants, and
  the truncation clause) and **dbt PASS=175** unchanged, since no dbt resource was added.
  `make live-site` runs 170 and `release_check` is clean on the live page.
- Still open, and now sharper: `scripts/evaluate.py` remains a three-row sample, and it is the only
  precision metric behind a rule that decides most postings. The audit measured this rule's live
  precision once, by hand, at a single point in time; nothing repeats that automatically. The
  collision census above is the cheapest candidate for a standing offline check, provided it is
  reported rather than enforced.

### 2026-08-22 - Increment 14

- **Coverage, measured on the 627-posting sweep of 13a and confirmed on the 628-posting sweep
  published here.** All three source blocks are present as an object on **627 of 627** and then
  **628 of 628** postings - better than the parent plan's recorded 98%/97%. The nullability sits in
  the `concept_id`, not the block: `employment_type` 0 null, `working_hours_type` **12**, `duration`
  **11**. Distinct codes are 4, 2 and 6, unchanged across all eight retained sweeps, and this sweep
  published **zero `Unrecognised code` rows**, so the vocabulary held on an eighth independent
  observation.
- **Published distributions, 628 postings each.** Employment type: Regular employment 428 ·
  Permanent employment (probationary period possible) 160 · Fixed-term employment 27 · On-demand
  employment 13. Working hours: Full-time 610 · Part-time 6 · **Not stated 12**. Duration:
  Open-ended 543 · 6 months or longer 40 · 6 months up to 12 months 20 · **Not stated 11** ·
  3 months up to 6 months 8 · 12 months up to 2 years 5 · 11 days up to 3 months **1**. Every
  column sums to 628 by inspection, which is the whole point of the row shape below.
- **The design deviates from the parent plan's `dimension / value_uri / value_label /
  posting_count` shape, deliberately.** Every posting lands in exactly one row per dimension: a null
  source `concept_id` is published as **`Not stated`** (`not_present`) and a code the reference does
  not carry as **`Unrecognised code`** (`unmapped`), with its code kept. 13a shipped a bug where the
  occupation column silently stopped summing to its own denominator once the ranking truncated, and
  `release_check` could not see it because its rule is that a denominator sentence exists, not that
  the two agree. A closed vocabulary of at most six values cannot truncate, so the honest move is to
  publish the unresolved buckets as rows and drop the denominator caveat entirely. The two
  unresolved kinds stay apart because they are two different facts: the source left the field empty,
  versus our vocabulary is out of date.
- `transform/tests/assert_requirement_totals.sql` is the machine-checkable form of that: each
  dimension's `posting_count` sums to the sweep's posting total, the grain is unique per
  dimension and value, and a sweep publishes all three dimensions or none. Deliberately
  **untagged**, so it ran against the live partitions under `make live-site` and passed. Its teeth
  were checked rather than assumed - re-run against a view with one dimension filtered out it
  reports `incomplete-dimensions`, and against a duplicated bucket both the sum and the grain
  branch fire.
- **The absent durations are informative, not missing at random.** Measured in 13a: all 11 postings
  without a `duration.concept_id` are `Behovsanställning` (on-demand employment), 11 of that type's
  13. That is exactly why `Not stated` is published as its own row instead of being dropped from a
  denominator - dropping it would delete the only signal that one employment type does not carry a
  duration at all.
- **The fifth employment type could not be established offline, and was not guessed.** The taxonomy
  declares 5 employment types; 4 have ever been observed, across eight sweeps. There is no taxonomy
  snapshot in the repo (`build_reference.py` only fetches over the network, and `working-hours-type`
  is not a valid taxonomy type - it returns 0 concepts), so `jobtech_requirement_labels.csv` carries
  the **12 measured rows**. This is a known gap, and it is safe rather than silent: an unobserved
  code arrives as a visible, counted `Unrecognised code` row. Whoever next runs `make reference`
  should add it. `test_requirement_reference_carries_the_live_vocabulary` pins the 12 observed codes
  as a subset, not an equality, so adding the fifth does not break the gate.
- **Open item, created knowingly: the page now mixes label languages.** The requirement dimensions
  publish our English labels (`Permanent employment`, `Full-time`, `Open-ended`) because
  "Tillsvidareanställning (inkl. eventuell provanställning)" is not usable text on an English page
  and this is a 12-row vocabulary under our control. The occupation and skill rankings publish
  Swedish ESCO labels, because ESCO 1.2.1 was pulled in the Swedish locale (13a's correction). So
  one page carries both, and the definition text says which is which rather than leaving a reader to
  infer it. Recorded here instead of being discovered later; not fixed in this increment, because
  re-pulling ESCO is a reference change with its own blast radius.
- `salary_type` is 100% present with 3 codes but only 89.6% single-valued (the parent plan's 94% is
  corrected), and `scope_of_work` is a `{min,max}` object that is null on all 627 - so both stay
  excluded, one for low information and one for having none.
- The nine new keys are `varchar` in the `read_json` `columns` map, in the `select`, and in
  `schema.yml`, with **no `not_null` on any of them**: the seven partitions collected before this
  increment have no such key and are NULL there permanently, because a stored partition is never
  rewritten. `requirement_demand_latest` therefore excludes a NULL status rather than rendering it
  as `Not stated` - a partition that predates the field is not the source declining to state a
  value, and inventing that row would be a lie about what was collected. Until a sweep lands the
  section is legitimately empty; a sweep carrying the status on only some of its postings would sum
  short and fail the assertion instead of publishing.
- `METHODOLOGY_VERSION` is **1.2**, pinned by a test. 1.1 published no requirement dimension at all,
  and two files named `...-methodology-1-1.csv` must not carry figures from two different definition
  sets. Same lesson as 13a, applied before the fact this time.
- The new sweep is `20260822T201202Z-f5cf1d409aa5`: **628 rows, 7 pages**, eighth partition, keyword
  scope. Denominators moved with it: region 598 of 627 to **599 of 628**, occupation 519 of 627 to
  **520 of 628**, skill 47 of 627 to **48 of 628** with 61 carrying a structured skill. The
  occupation ranking still truncates at 25 and still says so, accounting for 515 of its 520 mapped
  postings.
- `make sample` produced the diff it had to: `reference_hashes` is stamped into every manifest, so
  the new reference file rewrote all 5 rows of `sweeps_sample.ndjson`, and the nine keys rewrote
  every row of `postings_sample.ndjson`. The fixture now exercises both unresolved paths offline -
  one ad with a null `working_hours_type.concept_id` and one with a code no reference row carries -
  so `not_present` and `unmapped` are covered by the gate rather than only by the live page.
- `make check` green at **59 Python tests** (three added: the requirement triple across all three
  statuses, the reference vocabulary plus its presence in `reference_hashes`, and the methodology
  pin) and **dbt PASS=187**, up 12: the view, its eight `not_null` tests, two pinned vocabularies,
  and the totals assertion. `make live-site` runs 182 and `release_check` is clean on the live page.
- Noticed, pre-existing, not fixed here: `data/reference/reference_manifest.json` records
  `manual_reviews.csv` as `f7d72a98…` while the committed file hashes to `4898e357…`. That manifest
  is only ever written by the networked `make reference`, so it is stale for the two hand-maintained
  reference files, and the new one is absent from it for the same reason. Per-sweep provenance is
  unaffected - `reference_hashes` in every sweep manifest covers all five files - but the manifest
  should not be read as authoritative for hand-written references.
- **Review pass over the published commit, three findings fixed in a follow-up.** All three were the
  same shape - the page or a comment asserting an invariant no test enforced - which is the failure
  class 13a shipped and the reason this increment exists in the form it does.
  1. The definition text claimed `Not stated` meant "the source published the field but left its
     value empty". `requirement_mapping` returns that bucket for three source shapes: an omitted
     block, a block that is not an object, and an empty `concept_id`. The collector verifies none of
     them, so a renamed source field would bake 100% `Not stated` into an immutable partition and
     publish it under a sentence asserting the source left it blank - and nothing would fail: the
     totals still reconcile at 628 = 628 and `release_check` never inspects values. Reworded to
     "the source did not state a value for that field", which is true of all three shapes.
  2. `value_code` was the one leg of writer -> `SAFE_FIELDS` -> `columns` map -> `select` that
     nothing checked: it is nullable by design so a `Not stated` row invents no code, so a key
     misspelt at any of those four points would have published a whole dimension with an empty
     Source code column, permanently for that sweep, while the page kept promising the code is
     printed beside every label. `assert_requirement_totals.sql` now pins both directions - a
     resolved value carries its code, an unstated one does not - and passes on the live partitions,
     which is also the first positive proof that the code leg survived the wire.
  3. This commit created the repo's first heterogeneous partition history (7 partitions with none of
     the nine keys, 1 with all of them), and no committed fixture could express the old shape, since
     `make sample` builds every row through `normalize_jobtech_hit`. The `is not null` filter and
     the empty-view path were therefore exercised only by `make live-site` - the step that publishes,
     where a failure blocks every republish. A new test now runs the model's own SQL text against a
     synthetic legacy-shaped `stg_postings`: an all-NULL sweep publishes nothing, a half-migrated
     sweep fails the assertion on all three dimensions, and an all-collected sweep is silent again,
     so the test cannot pass by always failing.
- That new test earned its place immediately: it caught a stray ` to` line that an edit to the
  model's comment block had split out of a `--` comment, which would have broken `dbt run` for
  everyone. The gate found it before dbt did. `make check` is now **60 Python tests** / **dbt
  PASS=187** (no new dbt resource - the code-leg check is another branch of the same assertion), and
  `make live-site` 182 with `release_check` clean.
- Left as accepted suggestions rather than fixed: the three near-identical CTEs are combined
  positionally with `select *` and nothing pins which vocabulary belongs to which dimension (the
  sibling `dimension_demand_latest` is protected from that mistake by `assert_mapping_outputs.sql`
  pinning `taxonomy_version`); the page-level `Not stated` / `Unrecognised code` assertions are
  satisfied by the definition prose rather than by a table row; `order by dimension, posting_count
  desc, value_label` is not a total order once two unmapped codes share the `Unrecognised code`
  label; and the status assertion compares against the five-value `enrich.STATUSES` while the model
  contract pins three.

### 2026-08-23 - Increment 13b

- **Correction to the record: this file recorded 8 of the 29 tiebreak verdicts per concept, not all
  29.** Increment 14's plan deferred this increment on the strength of the claim that 13a "records
  every judgement call by concept id", which would have made 13b transcription plus a scoring
  decision. It does not. Every JobTech concept id that appears anywhere in this file amounts to 16
  distinct ids, of which 5 are sample fixtures (`CZkP_hCz_KM8`, `71Ji_irM_rSJ`, `3vry_gaE_yfQ`,
  `jBKc_5Yx_Y6T`, `qfkh_ZRK_w4W`), 2 are occupation-field scope ids (`apaJ_2ja_LuF`,
  `DJh5_yyF_hEM`) and 1 is the
  rival claimant that motivated the veto (`FHwx_yXu_FAd`). The 8 audited concepts recorded
  individually are the one `wrong` (`9yMK_8ep_D1K`), the four `narrower-or-broader`
  (`TU7g_mwa_VzB`, `XZaM_BRb_3mM`, `iXzD_6DF_sL4`, `uvcb_DuX_NW8`) and three `same` (`fg7B_yov_smw`,
  `Xnmr_kYS_YKY`, `xZLY_ZU5_E1q`). The other **21 `same` verdicts exist only inside the aggregate
  "24 `same`"**, and no fuller record exists in the repo or in `.kilo/`. Nothing was lost - 13a's
  kickoff asked for the verdict counts, every `wrong` concept and what was done about it, so the
  per-concept judgements were never captured - but they are judged first-hand here rather than
  transcribed, and every review row carries `13a-recorded` or `13b-rejudged` so a later reader can
  tell the two apart.
- **The live tiebroken population, re-derived offline before anything was judged.** Re-enriched the
  retained raw pages of the published sweep `20260822T201202Z-f5cf1d409aa5` (7 pages, 628 hits, 628
  distinct source ids) with `enrich_hit` against the pinned references: `exact_match_tiebreak` on
  **12 occupation concepts / 454 postings** and **16 skill concepts / 43 posting-mentions**. The
  rule *reaches* 13 occupation concepts / 455 postings; the thirteenth is `9yMK_8ep_D1K`, which now
  publishes `manual_review` because of 13a's veto, so it is scored here as an expected refusal
  rather than as a tiebreak. The same derivation over 13a's own sweep
  (`20260820T235159Z-f5cf1d409aa5`, 615 hits) returns **identical membership** - 13 occupation and
  16 skill concepts, none added, none dropped - with only two counts moved: `fg7B_yov_smw` 350 →
  357 and `rQds_YGd_quU` 81 → 84, so occupation 445 → 455 postings and skill 43 → 43. The 29
  concepts 13a audited are exactly the 29 the rule decides today, which is why re-judging the 21 is
  a re-judgement of the same population and not a new audit.
- **Pre-registered decision 1, how a `narrower-or-broader` concept scores. Written before any figure
  was computed, and it stands whichever way the figures fall.** The review row's expected URI is the
  URI the tiebreak chose, not `null`: 13a judged all four picks the best candidate ESCO 1.2.1
  contains and refused none of them, so writing `null` would assert the mapper ought to refuse -
  the veto decision 13a deliberately did not take for these four - and would collapse them into the
  expected-refusal case that belongs to `9yMK_8ep_D1K` alone. The doubt is carried by the verdict
  field instead, and the report publishes **two figures side by side off the same sample**:
  `strict`, which counts a `narrower-or-broader` row as a false positive because an inexact mapping
  is not the equivalence the crosswalk asserts, and `lenient`, which counts it as a true positive
  because it is the best target the reference contains. Neither is published as *the* precision, the
  gap between them is the honest size of the judgement, and a single flattering number is not an
  option this decision allows. `same` rows are true positives and `9yMK_8ep_D1K` is an expected
  refusal under both readings.
- **Pre-registered decision 2, the true-negative treatment.** A correct refusal - a row naming an
  occupation concept with `expected_occupation_uri: null` where the mapper produces no URI - is
  counted as a `true_negatives` and reported; an incorrect refusal stays a false negative, which it
  already is. `precision` and `recall` keep their textbook formulas, `tp/(tp+fp)` and `tp/(tp+fn)`,
  and true negatives enter neither: a metric whose name no longer matches its formula is worse than
  a missing metric. The report also carries the refusal pair `correct_refusals` /
  `incorrect_refusals` explicitly, so "the mapper declined, correctly" is legible without
  arithmetic. `occupation_concept_id: null` stays a different fact - the row does not test the
  occupation side at all - and is skipped there rather than scored as a refusal; conflating the two
  nulls would silently restore the hole this increment exists to close.
- **Pre-registered decision 3, the fate of the `skill recall < 1.0` pin
  (`tests/test_probe.py:593`).** It encodes "the metric is not trivially perfect", so it is
  re-expressed, never deleted. It stays as `skill recall < 1.0` provided the enlarged sample still
  produces at least one skill false negative - `review-002`'s `qfkh_ZRK_w4W`
  ("Python, programmeringsspråk"), whose single candidate `Python (datorprogrammering)` is a
  `broad-match` and therefore publishes `low_confidence` with no URI while the row expects that URI,
  is untouched by the new rows and should still supply it - and it gains two companions that make
  the property independent of that one row: the report shows at least one skill false negative, and
  at least one scored refusal. If the enlarged sample were to drive skill
  recall to exactly 1.0, the assertion becomes "the sample contains at least one mapping the mapper
  does not reproduce", read off the report's own counters instead of off the ratio. Either way a
  mapper that mapped everything and a mapper that refused everything must both fail the gate.
- **Verdicts: 23 `same`, 5 `narrower-or-broader`, 1 `wrong` - one disagreement with 13a's
  aggregate, published rather than reconciled away.** The 8 transcribed verdicts stand unchanged.
  Of the 21 re-judged first-hand, 20 are `same`: occupation `rQds_YGd_quU` Mjukvaruutvecklare,
  `rz2m_96d_vyF` Databasutvecklare, `bDCc_dTJ_qcd` Civilingenjör bygg, `QaQC_ozP_Bme`
  Rekryterare/Rekryteringskonsult, `FuJx_cGT_5im` Civilingenjör elkraft, `i1F4_cZZ_PJu`
  Systemarkitekt, `7TWG_1jQ_ULf` Datorlingvist, `KWFX_juL_yMb` Civilingenjör energi,
  `WWXN_Y22_6fy` Fordonsingenjör; skill `TMVb_DnH_etF` Agila arbetsmetoder, `kraG_fcm_3Mo`
  Felsökningsverktyg, `SaTd_K5z_ex1` AI, `XThy_HCH_FFc` Inbyggda system, `WQdS_Jtu_qPC` Android,
  `t78J_nRk_xGn` IOS, `iUew_moc_BRk` Programmering, `eBgZ_cwn_FN8` Spelutvecklingsverktyg,
  `bZ2o_tXM_Z9d` Sensorteknik, `5q4a_wi4_WYk` Molnteknik, `ksNo_7bD_ez3` Signalbehandling. The
  disagreement is **`muKv_rHW_7ES` `Testautomatisering/Test automation` → `utveckla automatiska
  programvarutester`, judged `narrower-or-broader` where 13a's aggregate counted it `same`**: the
  source is a competence area and the target is a single activity inside it, which is exactly the
  knowledge-concept-to-an-action shift 13a called `narrower-or-broader` for `Brandväggar`. ESCO's
  own nearer knowledge concept, `verktyg för automatisering av it-tester`, is marked `narrow-match`
  in the crosswalk, so there is no exact-level target to prefer instead.
- **Three judgements were close and were resolved on evidence, not on the label pair.**
  `KWFX_juL_yMb` `Civilingenjör, energi` → `energiingenjör` looks like a level-of-generality
  mismatch until the crosswalk is read: JobTech's separate `Gnrd_Brt_15j` `Energiingenjör` claims
  that same URI as a **`broad-match`**, so the reference does not treat the ESCO concept as broader
  than this one - `same`. `TMVb_DnH_etF` `Agila arbetsmetoder` → `agil utveckling` keeps its
  `same` because the genuinely narrower `agil projektledning` was offered and passed over as
  `narrow-match`. `bZ2o_tXM_Z9d` `Sensorteknik` → `sensorer` is `same` because ESCO names
  technology-knowledge concepts after the object (`signalbehandling` the same way) and the
  reference carries no `sensorteknik` to prefer.
- **The figures that followed the pre-registration, in the order the decisions demanded.** The
  sample is **32 rows**: the 3 crosswalk-regression rows from Increment 8 plus 29 audit rows, 13
  occupation and 16 skill. Occupation precision is **1.0 lenient and 0.857 strict** (14 true
  positives lenient, 12 with 2 false positives strict) with recall **1.0 in both**; skill is
  **1.0/0.95 lenient and 0.842/0.941 strict** (19 and 16 true positives, 3 strict false positives,
  1 false negative in both). The strict-lenient gap is the whole of the judgement and nothing else:
  no row moves between readings unless a reviewer judged it `narrower-or-broader`.
- **A refusal is finally an outcome.** `true_negatives` is **2** - `review-003` and the vetoed
  `9yMK_8ep_D1K`, whose expected non-mapping is now in the sample rather than absent from it - with
  `correct_refusals` 2 and `incorrect_refusals` 0. Before this increment both rows incremented no
  counter at all, so a mapper that refused everything would have reported `precision: null` instead
  of being penalised. `precision` and `recall` keep their textbook formulas; the true negatives sit
  beside them. Refusal counters are on the occupation side only, and deliberately: the skill side
  compares URI sets and has no way to say "expect nothing for this concept", so publishing a zero
  there would invent a measurement rather than report one.
- **Collision census: reported, enforced nowhere - and one figure of 13a's is corrected.** Under
  the definition that reproduces 13a's population figures exactly - a rival source concept the
  crosswalk also calls an `exact-match` on the chosen URI - the census is **34 of 277** tiebroken
  occupation concepts and **102 of 820** skill concepts, both reproduced to the digit. But live it
  affects **4 concepts, not 5**: `9yMK_8ep_D1K` (the one `wrong`), `XZaM_BRb_3mM`
  (`narrower-or-broader`), `Xnmr_kYS_YKY` and `xZLY_ZU5_E1q` (both `same`). That is 2 of 13 and 2
  of 16, which is what 13a's own "closely matching the 2-of-13 and 2-of-16 rates" sentence says;
  its next sentence said "5 live concepts", and that number does not reproduce. The looser reading
  - any relation claiming the URI - gives 18 live concepts and 142/357 in the reference, so it is
  not the definition 13a used either. The conclusion is unchanged and if anything sharper:
  enforcing sole claimancy would refuse 4 live concepts to catch 1 wrong mapping, so it stays a
  diagnostic. Reported in the committed report, with no threshold and no failing branch, and a test
  pins that the census function contains neither.
- **Four carry-overs from the Increment 14 review, all closed.** The three union branches in
  `requirement_demand_latest.sql` now name every column, because a positional `select *` would keep
  compiling while publishing one dimension's codes under another's labels. Each dimension's
  vocabulary is pinned separately in `schema.yml` with a per-dimension `accepted_values` on
  `value_code`, restricted to `mapping_status = 'mapped'` so an `Unrecognised code` row still
  publishes instead of blocking a republish - and its teeth were checked rather than assumed: a
  bogus mapped duration code fails only the duration pin, and the same code marked `unmapped`
  passes. A Python test reads both the reference CSV and those `accepted_values` lists and requires
  them to agree, so the two cannot drift while both look pinned. `scripts/publish.py` orders
  requirement rows by `value_code` last, because two unmapped codes share the label
  `Unrecognised code` and the previous order was not total. The page-level `Not stated` /
  `Unrecognised code` assertions now read the `<tbody>` of the dimension each belongs to; before,
  the definition prose satisfied them, so they would have passed on a page that dropped the rows.
  And the requirement statuses are compared against the three values
  `requirement_demand_latest`'s contract accepts, read out of `schema.yml` rather than restated -
  the five-value `enrich.STATUSES` would have accepted `ambiguous` and `low_confidence`.
- `make check` green at **63 Python tests** (three added: the two-nulls separation with the closed
  verdict/provenance sets, the sample covering the rule's live population, and the census being
  reported without a failing branch) and **dbt PASS=190**, up 3 for the per-dimension vocabulary
  pins. `make live-site` runs **185** and `release_check` is clean.
- **The negative check passed, which is the safety property of this increment.** Word-diffing the
  rebuilt page against the one published in Increment 14 gives **6 differing spans, all
  clock-derived**: `data-built`, the Page built stat, the footer time, the sweep age 0.1 → 0.7 days
  in both the column and its sentence, and the coverage age 1.3 → 17.4 hours. Token count identical
  at 5652. Every published figure - 628 postings, occupation 520 of 628, skill 48 of 628, all three
  requirement distributions, every mapping-quality count - is byte-identical. The report is not on
  the page, so `METHODOLOGY_VERSION` stays **1.2**: 13a's lesson was that a *rule* change under a
  stale version breaks traceability, and bumping for internal metric work would dilute that signal.
- **What this still does not measure, stated so it is not mistaken for more than it is.** The
  expected URI of an audit row is the crosswalk's own sole exact match, so the metric is a
  regression check plus a reviewed judgement of that pick - not an independent accuracy audit of
  live ads, which would need manually labelled postings. `EVALUATION_BASIS` says exactly that. The
  sample is pinned to the population of one sweep: a future sweep that carries a concept the rule
  reaches for the first time will not be covered until someone re-derives the set, and
  `test_review_sample_covers_every_tiebroken_concept_in_the_published_sweep` fails loudly if the
  reference moves the population instead of letting it drift silently.

### 2026-08-24 - Increment 16, pre-registration

Written before `scripts/insights.py` existed and before any figure was computed, because a gate
chosen after seeing whether it fires is not a gate. Everything below stands whichever way the
figures fall.

- **The trend gate: `TREND_MIN_SWEEPS = 14`, `TREND_MIN_SPAN_DAYS = 7`.** The span comes first
  because it is the binding idea. A daily bucket's active stock is one point-in-time reading taken
  at the last sweep in that day, so a day-over-day change is a single transition. Swedish postings
  are published on working days, which means a Friday-to-Saturday reading moves for calendar
  reasons and a Sunday-to-Monday reading moves the other way for the same reason. Seven days is
  the shortest span that contains every weekday once, so it is the shortest record in which a
  day-over-day claim can be read against data that holds its own counterexample. Below that the
  observatory cannot distinguish "demand rose" from "Monday is bigger than Sunday", and stating
  the former would be exactly the overstatement this increment must not make. The sweep count
  follows from the span: 14 complete sweeps is two per day across those seven days, the weakest
  cadence under which the last sweep of a bucket is plausibly near the end of that bucket, so two
  adjacent daily readings are taken at comparable points in their days rather than at whatever
  hour a single daily sweep happened to run. One sweep per day would satisfy the span while
  comparing a 06:00 reading against a 23:00 one and calling the difference a day of demand.
- **The trend rule reads the two most recent observed buckets and requires them to be adjacent. It
  never searches backwards for an older pair that happens to be adjacent.** Skipping over a gap to
  find a usable pair is the interpolation the guard forbids, wearing a different hat: it would
  publish a transition from days ago as though it were the current movement, and the sentence would
  be true of a period the reader is not looking at. A gap next to the newest bucket silences the
  rule, full stop.
- **`METHODOLOGY_VERSION` bumps to 1.3, pinned by a test.** The version claims to cover "the
  definitions, mapping rules, and suppression rule described on this page", and this increment adds
  published statements that are definitions in the only sense that matters: a median, a share, a
  superlative, each with its own rule for when it appears and which denominator it carries. Under a
  stale 1.2 a reader could not tell a page carrying those sentences from one that does not, which
  is 13a's lesson (a rule change under a stale version) rather than 13b's exception (internal
  metric work that publishes nothing). 1.2 published no derived sentence at all, so the bump is a
  fact about the page and not a courtesy.
- **No insight ever appears in a CSV export.** The CSV control serialises one table's `thead` and
  `tbody`; a sentence is not a row and would have to invent a column to become one. Exports stay
  tabular. Nothing is lost, because every insight is derived from the table it sits above, so the
  CSV of that table already contains the numbers needed to reproduce the sentence.
- **The precondition list the shared guard enforces, and the reason each one exists.**
  1. **A stated, non-zero denominator.** A rule refuses when its denominator is absent, zero, or
     not positive, and the denominator is interpolated into the sentence, so a sentence cannot
     exist without one.
  2. **Never read a suppressed cell.** `posting_flows` and `posting_survival` mask groups of 1 to 4
     by publishing NULL, which arrives as `None`. Any `None` the rule needs disqualifies it. The
     same treatment covers "never observed", which is also `None`, and both must be refusals: a
     rule that could tell them apart would be reconstructing the masked value.
  3. **One scope per sentence.** Every insight carries exactly one scope, and a rule handed rows
     from two scopes returns `None` instead of pooling them. No sentence names two scopes, two
     sources or two countries.
  4. **A share's numerator cannot exceed its stated denominator.** A >100% share is a caller bug,
     not a finding. This is not hypothetical: the skill column legitimately exceeds its
     mapped-posting denominator because a posting is counted in every skill it asks for, so the
     skill rule states a count against its denominator and must never turn it into a share.
  5. **A duration claim states the closed-posting count and carries the right-censoring caveat**,
     and refuses outright for a group flagged right-censored, because an open posting's duration is
     a lower bound and a median of lower bounds is not a median duration.
  6. **A trend claim** needs the two constants above, plus two adjacent most-recent observed
     buckets with an unsuppressed value in each.
  7. **Purity, so the rules are testable at all.** Rows in, `None` or `Insight(scope, text,
     evidence)` out. No query, no file, no clock. Every numeric token in the text is in `evidence`
     and in the rows it was built from, and a test proves that rather than trusting it.

### 2026-08-24 - Increment 16, completion

- **The trend gate fires or stays silent exactly as pre-registered: it stays silent.** The live
  data has 8 complete sweeps against `TREND_MIN_SWEEPS = 14` and 3 observed daily buckets
  (08-19 active 606, 08-20 615, 08-22 628) against a `TREND_MIN_SPAN_DAYS = 7` span, so the gate
  fails on both counts before the rule ever looks at a pair of buckets. And the one adjacent pair
  that does exist, 08-19 -> 08-20, is not the two most recent observed buckets, which are 08-20
  and 08-22 separated by the 08-21 gap - so the adjacency clause would have silenced it too. No
  trend sentence renders, and the reason is recorded here rather than implied.
- **Every non-gated rule fired and every sentence states its denominator, byte-matched against
  the tables beneath it.** Overview digest and section lines: "The latest complete sweep observed
  628 active posting(s) on 2026-08-22"; "The most frequently mapped occupation is
  IKT-systemutvecklare, in 382 of 520 mapped posting(s)"; "The most frequently mapped skill is
  C++, asked for in 16 of 48 posting(s) with a mapped skill"; "Of 628 postings in the latest
  sweep, 160 are permanent employment and 27 are fixed-term employment"; "Of 628 postings in the
  latest sweep, 610 are full-time and 6 are part-time"; "The median observed duration is 1.0 days
  across the 58 closed posting(s); postings still open are right-censored and are excluded."
  Each number was verified against the live rows the sentence was built from: the occupation and
  skill counts are the ranking's first row and the coverage denominator, the requirement counts
  are the published `posting_count` values, the duration median and count are the one closed
  basis (`inferred_absence`, 58 postings, median 1.0, not right-censored) with the caveat
  appended.
- **The rules that stayed silent, and why each one is silent.** The freshness/coverage warning is
  silent because the live scope is `fresh` and `covered` - an absence of a warning is not itself
  a finding. The trend rule is silent per the gate above. The fixture exercises the silence
  branches the live data does not: a suppressed duration group, a missing fixed-term or part-time
  bucket, a ranking tie, a count above its stated denominator, a gap next to the newest bucket,
  and a second collecting scope all render nothing.
- **`METHODOLOGY_VERSION` is 1.3, pinned by a test**, as pre-registered. 1.2 published no derived
  sentence at all, and the version claims to cover "the definitions, mapping rules, and
  suppression rule described on this page", so a page carrying insight sentences must not share a
  version with one that does not. No insight text appears in any CSV export: the CSV control
  serialises one table's rows, a sentence is not a row, and the table beneath each sentence
  already holds the numbers needed to reproduce it.
- **The traceability contract is a test, run over both the synthetic fixture and the live
  partition rows.** `test_insight_traceability_every_number_appears_in_the_source_rows` asserts
  that every numeric token in every generated sentence appears in the rows it was built from; a
  re-run against the live `dev.duckdb` rows reports the same sentences and no missing token. The
  contract also forced a wording choice worth recording: percentages are derived numbers the rows
  cannot vouch for, so the employment and working-hours rules state the two counts and the total
  and let the reader see the share - "160 permanent and 27 fixed-term of 628 postings", never a
  percentage.
- **Three carry-overs from the 13b review, closed.** (1) `tests/test_probe.py` now anchors the
  vocabulary-guard block on `- {name: value_label`, the flow-style the schema actually writes,
  instead of a `- name: value_label` that never matches and silently spanned the rest of the
  file. (2) `scripts/evaluate.py`'s `_sole_exact` is gone; the tiebreak predicate now lives once,
  as `enrich.sole_exact_match`, used by `enrich._mapping`, the collision census, and (indirectly)
  the sample-coverage test, so there is no second copy to drift. (3) The three error-severity
  `accepted_values` pins on `requirement_demand_latest.value_code` are now `severity: warn`,
  because they run on the publish path against immutable partitions and a newly observed mapped
  code must never hold up every republish while the pin catches up; the Python test still
  requires the pinned list and the reference file to agree. The equality assertion was kept, not
  relaxed to a subset, because a subset would let the pin lag while dbt silently blocked - the
  worse failure mode.
- **`make check` green at 70 Python tests** (seven added: the firing set with denominators, the
  traceability contract, the one-scope sentence property, the unmet-precondition silence, the
  freshness warning, the trend gate firing case, and the two-scope refusal; plus the 
  `METHODOLOGY_VERSION` pin moved to 1.3) and **dbt PASS=190 WARN=0** unchanged, since the
  severity change alters a test's config, not the resource count. `make live-site` runs 185 with
  the fixture-tagged tests excluded, and `release_check` reports 0 problems on the live page,
  including the two new rules: no empty insight paragraph, and the Overview digest present
  whenever the page renders any insight.

### 2026-08-31 - Scope decision: Germany is a sample, not a census

Planning session. No code, no partitions, no data, no gate: only `FUNCTIONALITY_ROADMAP.md`,
`USER_MANUAL.md` and this file changed.

- **The decision.** The sister scraper lab is descoped from a full German census to a **stratified
  region-bounded sample with a capped within-stratum draw over a frozen panel**. The observatory's
  job is to be ready to publish that, which is a publishing problem rather than a modelling one. The
  design is neither a census nor a partial crawl, and the wording matters: a partial crawl is a
  census that failed, while this is a sample that was drawn on purpose and can be described.
- **Four earlier planning assumptions were wrong, and each was checked against this checkout before
  being written down.** (1) *There is no map.* The regional surface is a top-25 table:
  `_query_dimension(region=True)` (`scripts/publish.py:689-701`, called at
  `scripts/publish.py:1653`) truncates at `DIMENSION_LIMIT = 25` (`scripts/publish.py:24`), so
  regions below 25th are collected, stored and mapped but never rendered. (2) *There is no 85%
  mapped-share ratio anywhere in code.* `_denominator` (`scripts/publish.py:1132-1170`) publishes
  three counts and deliberately no percentage — its own docstring gives the reason, that a ratio
  invites a coverage trend one sweep cannot support — so no mapped-share threshold exists to be
  quoted as a gate. (3) *The suppression floor of 5 is not a regional rule.*
  `transform/macros/suppress_small_counts.sql` masks non-zero groups under 5 in `posting_flows` and
  `posting_survival` only, and neither view has a region column
  (`scripts/publish.py:775-798`); a thinly sampled region is therefore absent from the top 25 rather
  than `suppressed`. (4) *No test enforces country-level exhaustiveness.* Completeness is judged
  inside the declared scope — `status = 'complete'`, pages matching, `expected_rows = row_count`
  (`transform/models/staging/stg_collection_manifests.sql:50-53`) — and coverage turns `invalid`
  only on a manifest/row disagreement or a wrong-country row
  (`transform/models/publish/source_coverage.sql:68`). **Sampling needs no transform change at all**,
  which is why this session is documentation and not a migration.
- **The plan is Increments 20-25**, recorded in the roadmap with the brief's budgets: widen the
  `jobtech`-only live globs (`Makefile:25-26`, `Makefile:94-96`); replace `_verify_single_scope`
  (`scripts/publish.py:756-772`) with per-scope and per-country sections and scope
  `_query_dimension`/`_query_skills`/`_query_mapping` (`scripts/publish.py:689-701`, `704-714`,
  `716`) with it; add the breadth line "N of 400 DE NUTS-3 regions with mapped postings" to the NUTS
  block of `_render_countries` (`scripts/publish.py:1117-1128`, function at
  `scripts/publish.py:1056`) with the sampling caveat sourced from `coverage_limitations`; map German
  occupations over stored partitions through the `scripts/enrich.py` path; bump the methodology
  version with the sampling text; then, optionally, the live service.
- **The order is deliberate: 20 before 21, and the build stays red in between.** Widening the globs
  makes German partitions visible, at which point a second scope carrying postings trips
  `_verify_single_scope` and fails the build **by design** — that guard is the only thing stopping
  two scopes being summed into one ranking under a denominator naming a single sweep. It is removed
  when the per-scope sections that make pooling unnecessary exist, not before.
- **One correction to the brief itself: the methodology bump is 1.3 to 1.4, not 1.2 to 1.3.**
  `METHODOLOGY_VERSION` is already `"1.3"` (`scripts/publish.py:74`), bumped by Increment 16 on
  2026-08-24 and pinned by a test. The brief's "1.2 → 1.3" predates that bump, and the checkout wins.
  The `coverage_limitations` text changes with it: the strings are constants
  (`scripts/collect.py:55-63`) pinned by equality at `tests/test_probe.py:884` and
  `tests/test_probe.py:1047`, so constants and pins move in one commit.
- **Increment 18 (German access request) is cancelled, with the text kept.** It was premised on
  census-level coverage — a BA data agreement as "the only real unlock", asking for complete
  traversal or snapshot semantics. A sampled panel needs no agreement to publish, and the census it
  would have authorised is now explicitly out of scope. The roadmap's stale "Do not shortcut Germany"
  recommendation and its equally stale "next step is Increment 12" were replaced by Increment 20,
  with the superseded wording quoted in place rather than deleted. Increments 15, 17 and 19 stay
  recorded but unscheduled: they are outside the finish line, not wrong.
- **Acceptance criteria recorded:** `make check` and `make release-check` green; the page rendering
  all countries in per-country sections; German breadth at ≥390 of 400 NUTS-3 regions with mapped
  postings; `collection_frequency.complete_sweeps` ≥ 3 for the German panel
  (`transform/models/publish/collection_frequency.sql:28`); and the occupation section populated for
  Germany.
- **Stop rule, recorded verbatim in the roadmap:** "items 1-5 are the finish line. No StepStone, no
  Kimeta, no Indeed, no census completion, no other-country re-sweeps unless the live-service budget
  allows." Items 1-5 are Increments 20-24; item 6 is Increment 25 and optional.
- **Two files were reviewed and deliberately left unchanged.** `README.md` states no census claim to
  correct: it already frames itself as an aggregate record with a denominator beside every ranking,
  and its suppression paragraph already scopes the rule to the flow and survival views. Its stale
  "Methodology version 1.2" (`README.md:20-21`) is a version error, not a census claim, and Increment
  24 owns it. `SOURCE_FEASIBILITY.md` states no census-level coverage target: every completeness
  claim in its rows is scope-bounded, and its Fixed Release Scope already says a sweep means "all
  pages for one fixed query scope, not all Swedish vacancies".
- **One open conflict left for the operator, not resolved here.** `SOURCE_FEASIBILITY.md` still reads
  "the project must not collect or publish German posting observations yet", which collides with
  publishing the sister lab's German panel. Editing that governance decision was outside this
  session's brief, and the German source's own feasibility record lives in the sister lab's
  documents. It needs a decision recorded there and mirrored here before German rows reach a
  published page.
- **Carry-overs for Increment 24, both cosmetic and both version-related:** `README.md:20-21` claims
  methodology 1.2, and the manual's CSV example (`USER_MANUAL.md:127`) still shows
  `...-methodology-1-2.csv`. Both are wrong today at 1.3 and must land on 1.4 with the sampling text.

### 2026-09-01 - Increment 20: widen the live globs

Makefile-only session. Three globs changed, nothing else: no collector, no dbt model, no publisher,
no test, no partition moved. Both gate runs bracket the edit.

- **The defect.** `make live-site` resolved exactly one source directory. The sweep count globbed
  `data/raw/collections/jobtech/*/*/manifest.json` (`Makefile:25-26` before the edit) and the recipe
  exported `OBSERVATIONS_PATH` and `MANIFESTS_PATH` under the same `jobtech/` prefix
  (`Makefile:94-96` before the edit), so a partition from any other collector could sit on disk,
  pass every gate and still be invisible to dbt and to the page.
- **Depth confirmed before editing, not assumed.** One precise glob
  (`data/raw/collections/*/*/*/manifest.json`) resolved 8 manifests, the same 8 as
  `data/raw/collections/jobtech/*/*/manifest.json`, and the two inner segments read as a scope id
  (`jobtech-f5cf1d409aa51fad`) and a sweep id, so the stored shape is `source/scope_id/sweep_id` and
  the segment count after `data/raw/collections/` is three. Only `jobtech` exists under
  `data/raw/collections/` today. No recursive listing of `data/` was taken.
- **The change is a widened source segment at fixed depth.** `LIVE_SWEEPS` (`Makefile:29`) and both
  exported paths (`Makefile:101-102`) now read `data/raw/collections/*/*/*/`. Depth is the whole
  correctness argument: one segment more or fewer would resolve a different set of manifests while
  still looking plausible, which is why the comment at `Makefile:24-28` now says to widen the source
  segment and never the depth.
- **Fail-closed behaviour untouched.** `LIVE_READY` (`Makefile:30`) is byte-identical: it still
  expands to `$(error no stored sweeps found; ...)` when the wildcard is empty, so an empty page is
  still unpublishable. Widening the glob widens what can be found, not what counts as enough.
- **Measured, and the count is the test.** `make live-site` printed **8 stored sweeps before the
  change and 8 after** — identical, as required, since only `jobtech/` is on disk. A different
  number would have meant a wrong glob depth rather than a discovery, and would have been fixed
  rather than accepted. dbt on the live partitions ran PASS=185 WARN=0 ERROR=0 both times with
  `tag:sample_fixture` excluded, and the page wrote `site/build/index.html` unchanged in shape.
- **Gates.** `make check` green before and after (70 pytest, dbt PASS=190 WARN=0 ERROR=0, ruff and
  mypy clean, fully offline); `make release-check` green with `0 problem(s)` on the built page. No
  test and no `check` target was edited, and nothing under `data/` was written.
- **What this deliberately does not do.** No German data is published, because none is on disk: the
  increment makes the path reachable, not populated. No collector was added or touched, no dbt model
  changed (staging reads whatever the globs resolve to, and completeness is judged inside the
  declared scope), and no source-specific special case was introduced — the widened glob is
  collector-agnostic by construction.
- **Stated plainly, because it is the next thing an operator will hit:** widening the glob alone will
  trip `_verify_single_scope` (`scripts/publish.py:756-772`) the moment a second scope carries
  postings. That failure is **by design** — it is what stops two scopes being summed into one ranking
  under a denominator naming a single sweep, since `_query_dimension`, `_query_skills` and
  `_query_mapping` read their views with no scope filter — and removing it is Increment 21's job,
  not this one's. Today the build is green only because `jobtech`'s second scope carries no postings.
- **Comments kept truthful.** `Makefile:24-28` and the `live-site` block at `Makefile:90-93` both
  described jobtech-only behaviour by implication; they now state that every collector's partitions
  are read, why the depth is fixed, and that the per-scope guard is the next barrier.


