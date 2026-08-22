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

