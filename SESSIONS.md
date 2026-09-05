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
| 20 (re-applied) | 2026-09-03 | Complete as code this time; the widened glob is committed, and the intended next failure turned out to be two earlier ones | Re-apply Increment 20, whose 2026-09-01 record survived a merge but whose Makefile edit did not: `git log -- Makefile` stopped at `c9ade31` and the commit claiming increment 20 (`1a2b6be`) touched only `.gitignore` and `SESSIONS.md`, so all three globs were still `jobtech/*/*/`. Widened the source segment only, at unchanged depth: `LIVE_SWEEPS` (`Makefile:30`) and the exported `OBSERVATIONS_PATH`/`MANIFESTS_PATH` (`Makefile:103-104`); `LIVE_READY` (`Makefile:31`) left byte-identical. Depth verified by count rather than by reading: the depth-3 glob resolves 9, which equals 8 `jobtech` + 1 `ba`, and the depth-4 glob resolves 0. `make` itself confirms it, printing `publishing from 9 stored sweeps`. Also resolved six committed merge-conflict markers in this file (two blocks, at the table and before the 2026-08-31 scope note); both kept HEAD and the `scrapers` side was empty, so only the marker lines were removed and no recorded line was lost. Makefile and SESSIONS.md only - no collector, dbt, publisher, test or data change. | `make check` green (ruff, mypy 62 files, **459 passed**, dbt PASS=190 WARN=0 ERROR=0). `make live-site` **red by design, but earlier than predicted**: it fails in `dbt build` (PASS=183 ERROR=2) before `scripts/publish.py` runs, so `_verify_single_scope` was never reached. `make release-check` not run - it builds on `site`, not `live-site`, and would only have re-tested the sample |
| 20b | 2026-09-03 | Complete; dbt build is green on live partitions, and the failure has moved to the per-scope guard as planned | Admit the BA mapping vocabulary into the pinned `accepted_values` list and backfill 12 NUTS-3 labels via a new `stg_nuts_labels` model coalesced in `stg_postings`, so `make live-site` gets past `dbt build` and dies in `_verify_single_scope` (Increment 21's job). Ten BA method values registered - six observed in the `ba/de-nuts3-panel` partition plus four (`ba_segment_radius_nuts3`, `ba_plz_nuts3`, `ba_plz_ambiguous`, `not_available`) pre-registered from a source audit of `scrapers/ba_jobsuche.py` so a future PLZ/radius sweep cannot redden the build; other collectors' ~35 literals deliberately absent. `stg_nuts_labels` reads the nine reference CSVs explicitly (no glob - it would miss the two Slovak `mpsv` files), one row per code by `group by`, pinned by contract + not_null + unique; `assert_nuts_label_unambiguous` (untagged, runs under live-site) surfaces cross-file label conflicts. Coalesce is source-wins in `stg_postings` (`:18`), left-joined so `not_present` rows keep their denominator. Prevention fix applied too: `GermanCrosswalk.label_for_nuts` now feeds both Tier-3 resolutions in `ba_jobsuche.py:1186-1204`, so a re-sweep stops reproducing the null. | `make check` green (ruff, mypy 62 files, **459 passed**, dbt **PASS=195** WARN=0 ERROR=0; new model + 3 tests + 1 singular test). Live rebuild PASS=190 ERROR=0; fan-out guard: `stg_postings` 33,836 rows unchanged, BA region outcomes sum to 28,900, BA region rows still 393, all 12 codes labelled (`DE937` Rotenburg (Wümme), `DEB11` Koblenz, Kreisfreie Stadt), zero null-label rows. `make live-site` red exactly as planned: dbt green, then `ValueError: 2 scopes have postings` in `_verify_single_scope` (`publish.py:768`) |
| 21 | 2026-09-04 | Complete; the two-scope page publishes, each scope in its own sections with its own denominators | Governance first, own commit: `SOURCE_FEASIBILITY.md` gains a dated amendment (owner-relaxed ToS/robots gate 2026-08-23, BA Jobsuche an active lane via `scrapers/ba_jobsuche.py`, German data a stratified region-bounded sample over a frozen 400-region NUTS-3 panel), the BA row's `Rejected` verdict superseded not rewritten, the German scope added to Fixed Release Scope, and the Approval Gate recorded as **unmet** - the relaxation is the owner's decision, not a BA approval. Publisher second: all five pooled surfaces scoped by `(source, scope_id)` - `_query_dimension`/`_query_skills` take `DIMENSION_LIMIT` **per scope** via `qualify row_number() over (partition by source, scope_id, dimension ...)`, `_query_mapping` groups within scope dropping the cross-scope sum, `_query_requirements` carries the scope key, and `_denominator` (`publish.py`) names its own sweep or says it has none. Countries/Occupations/Requirements render one subsection per scope (`h3` scope, `h4` topic blocks, table ids suffixed `-{source}-{scope}`), the quality missing-mappings table is per scope too, and the region ranking gains its denominator plus the unlisted-tail sentence - material now that truncation is 25 of 393. `insights.build` partitions per collecting scope (`_collecting_scopes`, demand order, `active_postings > 0`) so `_requirement_count` and the share totals read one scope; the scope label is markup beside the sentences (`<p class="label">`), never inside `Insight.text`, so the traceability test still passes unmodified. `release_check` matches ranked tables by **id prefix** (`table-countries-regions`, `table-occupations-ranked`, `table-occupations-skills`), at least one per prefix, each with its own consumed denominator; `https://www.arbeitsagentur.de/` registered as the BA licence host the manifests cite. The false "Sweden only: no German posting source has passed the approval gate" clause dropped; `data/sample/` deliberately not regenerated (the hand-built DuckDB test covers the two-scope shape); no METHODOLOGY_VERSION bump (Increment 24). The two refusal tests replaced by behaviour tests keeping their intent; the one cross-scope figure left standing is the Status section's pre-existing operational "row(s) stored by the latest sweep of each scope" storage stat, which was already cross-scope in the single-source fixture (20 = 11 + 9) and is not a demand count. | `make check` green (ruff, mypy 62 files, **459 passed** - two tests replaced one-for-one, dbt **PASS=195** WARN=0 ERROR=0 unchanged). **`make live-site` completes for the first time on two scopes**: `publishing from 9 stored sweeps`, dbt PASS=190 ERROR=0, `wrote site\build\index.html (2 rows)`. Live-page release check **0 problems** (`uv run --offline python -m scripts.release_check site/build/index.html`, run directly - `make release-check` would rebuild the synthetic page over it; run separately, green). Spot-check: DE region subsection lists 25 regions with the tail sentence ("Ranked from 28,603 mapped posting(s) of 28,900 ... accounting for 2,729 ... unlisted tail"), DE occupation/skill rankings empty with honest denominators ("Ranked from 0 mapped posting(s) of 28,900 ... 0 carry a structured occupation" - Increment 23's job), SE denominators name their own 628-posting sweep, digest labels each scope group, no pooled demand figure |
| 22 | 2026-09-04 | Complete; the German breadth count is published from a pinned frame, as a count and never a share | New dbt view `region_breadth_latest`: `count(distinct value_uri)` over `dimension_demand_latest` region rows per `(source, scope_id)`, joined to the NUTS-3 frame in `stg_nuts_labels` (`length(nuts_code) = 5`, grouped by `left(nuts_code, 2)`), so the denominator is the pinned reference frame and **not** the Sweden-only `geography_nuts_2024.csv` and the count is **not** the number of rendered region rows (those truncate at `DIMENSION_LIMIT = 25`). `assert_nuts_frame_counts` (untagged, runs under live-site) pins the frame at exactly 400 DE / 21 SE. The publisher's `_query_region_breadth` feeds each scope's region block with the breadth line and the manifest's own `coverage_limitations` string rendered verbatim above the denominator, `class="definition"` so `release_check` still consumes the real denominator. A null frame degrades to an explicit no-frame sentence, never "N of 0", and no percentage is rendered anywhere. | `make check` green (ruff, mypy 62 files, **459 passed**, dbt **PASS=201** WARN=0 ERROR=0; +1 model, +5 tests). Live cross-check: `regions_with_postings = 393` for `ba/de-nuts3-panel` against the 400-region frame, matching the 20b measurement; SE 21 of 21. Live-page release check 0 problems |
| 23 | 2026-09-04 | **Cancelled** - unimplementable from this source, evidence recorded; the gap is published as data instead of a ranking | Three confirmations in the sister lab's checkout: `scrapers/ba_jobsuche.py:51-52` (search page carries only a free-text title, no occupation code), `scrapers/ba_jobsuche.py:1222-1246` (`NormalizedRecord` built with `esco_occupation_uri=None`, `occupation_mapping_status="not_present"`, method `not_available_ba_html` - no occupation input exists in the stored partition to map), `scripts/sanitize.py:31-35` (allowlist carries only mapping outputs; no title field, and the published methodology commits to never classifying titles or free text). Acceptance criterion 5 was written when Germany was expected via HR-BA-XML, which would have carried occupation codes; it is **unachievable from this source**. In place of the ranking, `_empty_by_construction` renders one sentence in any scope whose `mapping_coverage_latest` row reports `postings_with_source_value = 0` with `postings_total > 0` - for occupation and skill alike - derived from the data alone, no source names, no German special case. `SOURCE_FEASIBILITY.md` appends the occupation-field gap to the German fixed-release-scope entry; the roadmap marks the increment Cancelled with the citations and the two revival conditions (a structured-field source, or an evaluated title-classification method the project has ruled out). | `make check` green (459 passed, dbt PASS=201); live-page release check 0 problems; the DE occupation and skill blocks carry the empty-by-construction sentence beside "Ranked from 0 mapped posting(s)" |
| 24 | 2026-09-04 | Complete; the published methodology describes a sampled design and an occupation gap | `METHODOLOGY_VERSION` 1.3 -> 1.4 (`scripts/publish.py`, the test pin moved in the same commit). The on-page methodology text now states that `ba/de-nuts3-panel` is a stratified region-bounded sample with a capped within-stratum draw over a frozen 400-region NUTS-3 panel - not a census and not a partial crawl, with the panel's own manifest caveat beside its figures - while the Swedish keyword scope is a keyword-scoped query, not a sample; and that one published scope carries no structured occupation field, so its occupation and skill rankings are empty by construction. Together with 22's breadth count this is a definition change, not a wording tweak. `collect.py`'s limitation constants deliberately untouched: Task 0 verified nothing pins the committed sample to them (only `tests/test_probe.py:884`/`:1047` pin runtime manifests to the `collect.*` symbols) and their text is not false, so no `make sample` regeneration was forced. `README.md` corrected 1.2 -> 1.4 with the two scopes, the sampling design, the occupation gap and the `docs/index.html` artefact; `USER_MANUAL.md`'s CSV example now reads `...-methodology-1-4.csv`. Interpolations at footer, `data-methodology-version` and CSV filenames move with the constant; `release_check.py`'s version rule untouched and confirmed to follow it. | `make check` green (459 passed, dbt PASS=201); methodology 1.4 verified in the footer, the `data-methodology-version` attribute and a CSV filename on the live page |
| 22/23/24 wrap-up | 2026-09-04 | Complete; the finish line is reached and visible | The one-increment-per-session rule (`SESSION_RUNBOOK.md:40-52`) **suspended for this session by owner decision** - it exists to stop two agents colliding in `publish.py`/`SESSIONS.md`, which is not the situation, and it was costing three more plan-and-record cycles for ~3 h of work; scope was not widened. Four commits in task order (`ef3f65a`, `12412d0`, `8db030a`, `2a4e537`), each verified with `git show --stat HEAD`. `docs/index.html` committed as the portfolio artefact: a copy of the live two-scope page (footer "built from stored collection partitions", German 28,900 headline, 393-of-400 breadth line with the manifest caveat, empty-by-construction sentences, methodology 1.4), release-checked at 0 problems; `site/build/` stays ignored and ephemeral. `SESSION_RUNBOOK.md` section 3 gains the ordering rule: finish with `make live-site`, never `make release-check`, because release-check rebuilds the synthetic page over the live one. | Gates as run: `make check` (459 pytest, mypy 62 files, dbt PASS=201 WARN=0 ERROR=0); `make release-check` on the synthetic page (0 problems); `make live-site` (9 stored sweeps, dbt PASS=196 ERROR=0, 2 demand rows); direct release check on the live page and on `docs/index.html`: 0 problems each |
| Sweeps restart (Plan 1 Task 1) | 2026-09-04 | Complete; the first post-pause Swedish sweep is stored, published and committed, and the cadence is re-established | Restarted the Swedish collection cadence after 11 idle days, exactly as pre-flighted. One sweep (`20260904T183925Z-f5cf1d409aa5`, 623 rows, 7 pages) from the main checkout: 9 `jobtech` partitions now on disk, `ba` still 1, nothing existing rewritten (git clean after). Gates in the runbook's order. `docs/index.html` refreshed from the live build and committed (`541e47c`). Cadence rule for the coming days: never slower than every two days, design target twice daily. | `make check` green (459 pytest, dbt PASS=201); `make release-check` green on synthetic (0 problems); `make live-site` green (10 stored sweeps, dbt PASS=196, 2 rows); direct release check live page + `docs/index.html`: 0 problems each |
| German panel sweeps 2 and 3 (Plan 1 Task 2) | 2026-09-04 | Complete; `complete_sweeps = 3` for `ba/de-nuts3-panel`, criterion 4 met, both scopes Fresh on the published page | The "sister lab" turned out to be in-repo after the `merge/scrapers-lab` merge: `main.py --source ba --panel` drives the frozen-panel sweep (`scrapers/ba_jobsuche.py` `_fetch_panel`), `PANEL_HANDOVER.md` §3 is its runbook, `scripts/check_ba_panel_readiness.py` is the DoD gate, and `data/reference/ba_panel_nuts3.json` is the committed pinned panel. Sweep 2 (`20260904T201534Z`, observed 2026-09-04): 400 region queries, 398 with rows, 1321/1321 pages, 0 failed (29 absorbed 403s), 29,068 rows. Sweep 3 (`20260904T210722Z`, observed 2026-09-05): identical shape, 29,068 rows. Both verified against the plan's §3.2 cross-checks and the panel DoD (all six PASS across all 3 partitions); both committed to `docs/index.html` (`e25a94d`, `9bd4563`). | Panel DoD: 3/3 partitions reconcile, membership hash `545b162ec6e5fbdc...` identical across all 3 sweeps, 0 failed requests (77 absorbed throttles total), PII clean, cap-as-scope declared. `make live-site` green (12 stored sweeps, dbt PASS=196 ERROR=0); direct release checks on live page + `docs/index.html`: 0 problems each |
| Cadence guard (Plan 1 Task 3) | 2026-09-04 | Complete; abandonment is now a red dbt gate, ordinary staleness stays a page badge | One new untagged singular test `transform/tests/assert_cadence_not_abandoned.sql` (commit `f8a8425`): fires when a scope's latest complete sweep is older than 4x its own `freshness_threshold_hours`, reading reference time through the same `OBSERVATORY_REFERENCE_TIME` mechanism as `source_coverage` so it is deterministic offline. Green on the committed sample by measurement (largest sample multiple 171/48 = 3.6x) and green under `live-site`; the red side is proven on the measured 2026-09-04 morning state (jobtech 308.5 h at 48 h = 6.4x would have failed, ba 64.7 h at 24 h = 2.7x would not - exactly the abandonment-vs-staleness split the test exists for). No Makefile, gate or constant edits; scope one test only, no scheduler, no notification channel. | `make check` green (459 pytest, dbt **PASS=202** WARN=0 ERROR=0, +1 test); `make live-site` green (dbt PASS=197 including the new test untagged); release checks 0 problems |
| Trend rule check (Plan 1 Task 4) | 2026-09-04 | Complete; `rule_trend` stays **silent** on both scopes, each unmet precondition named with its measured value | Measured after all sweeps: jobtech `complete_sweeps = 9` (< 14) and its newest daily buckets are 08-22 -> 09-04, a 13-day gap adjacent to the newest (the no-gap precondition fails); de-nuts3-panel has adjacent newest buckets (09-04 -> 09-05) but `complete_sweeps = 3` (< 14) and span 3 d (< 7). No constant, threshold or precondition touched; the silence is the pre-registered behaviour. The rule will become evaluable once the Swedish cadence holds. | Direct measurement of `collection_frequency` and `posting_flows` (day grain) per scope; `rule_trend` re-run from `scripts.insights` against the live rows: SILENT for both scopes, as expected |
| Uniform inferences + UI redesign (owner direction: presentation and simple inferences) | 2026-09-05 | Complete; methodology **1.5**, two uniform statistical rules firing on both scopes, and the guideline-reviewed instrument-board redesign implemented from `design/UI_REDESIGN_SPEC.md` | **Owner decisions recorded:** (1) the no-new-dependency rule is **lifted** - presentation libraries and premade assets are allowed, `make check` stays offline as the API-quota firewall, vendored inline assets are the pattern (Increment 15's uPlot spec already wrote the policy). (2) Occupation-type inferences stay **out entirely** - Germany's source carries no occupation field, and the app stays uniform across scopes: no per-country special casing. Inferences added, both computed per scope from rows the page already publishes: `rule_region_concentration` (leading region's count against the **mapping_coverage** mapped total - never the truncated ranking column, which sums to the top-25 listed) and `rule_sweep_churn` (openings/closures/active between the two most recent daily buckets, spacing stated; no direction claim so no cadence gate). Redesign ported from the spec/prototype: housing-plate header, mode selector, **observation board** (one card per scope: lamps, count, frame strip, trend line - replaces the cross-scope-inviting "Largest single observation" stat), **scope plates** in Countries/Occupations/Requirements, **annunciator lamps** with age/threshold numbers in every table, **frame strips** (per-tick SVG ≤60 regions, pattern-runs otherwise, unique ids via context suffix), **mark key** (filled/hollow/hatched/dashed), **absence plates** replacing the five empty German tables (occupation, skill, employment, hours, duration - requirement condition = empty dimensions + positive posting total, spec Flag 1 option b), **mapping chips** (three-segment mapped/carries/total), hatched suppressed cells, `Not stated`/`Unrecognised code` row markers, `theme-color`, amber+ink focus ring, Data Register monospace numerals, `translate="no"` on scope ids. Commits: `3bbf640` (rules + redesign + tests), `f126600` (design spec/prototype/screenshots tracked), `69bdf1e` (artefact). | `make check` green (ruff, mypy 62 files, **459 pytest**, dbt **PASS=202**); `make release-check` green on synthetic; `make live-site` green (12 sweeps, dbt PASS=197, 2 rows); direct release checks live + `docs/index.html`: **0 problems**; live page verified: 2 board cards, 6 scope plates, 5 absence plates, 4 frame strips, 2 chips, 24 lamps; concentration "Rendsburg-Eckernförde, 187 of 28,779 mapped" (correct sweep denominator), churn "13 opened and 13 closed" (DE, one day apart) |
| Context reset + Plans A/B + Plan A Task A1 (owner direction: dry/bland/technical is the big issue; sweeps automation undelivered; context hygiene) | 2026-09-05 | Complete; two plans written for multi-session execution, MEMORY.md rewritten as the de-poisoned handoff, and A1 (plain-language board) implemented | **Owner direction, recorded verbatim-intent:** (1) "The application looks dry, bland and technical for an average user. That is the big issue" - the quiet-instrument aesthetic is **superseded** (banner added to `design/UI_REDESIGN_SPEC.md`; its a11y chapters stay binding). (2) Local sweep automation was asked for and not delivered - Plan B exists now. (3) Fear of context poisoning / outdated guardrails - **MEMORY.md rewritten fresh** with an ACTIVE-vs-RETIRED guardrail list (§4): no-new-deps and the quiet-instrument aesthetic are RETIRED; data honesty (per-scope separation, traceable numbers, denominators, suppression, offline check, no-JS readability, methodology bumps on new figures) is ACTIVE. Plans: **A** `.kilo/plans/1788618000000-dynamic-user-friendly-presentation-plan.md` (A1 plain-language board, A2 vendored-uPlot charts, A3 `<details>` decluttering, A4 five-section IA optional), **B** `.kilo/plans/1788618000000-local-sweep-automation-plan.md` (B1 `make auto` orchestrator that never commits a red gate, B2 Windows scheduled tasks + BA-daily-vs-weekly cadence decision). **A1 implemented this session:** board cards gain friendly fact lines rendered from insight-rule **evidence** (numbers identical to the formal sentences by construction): "Most postings sit in Rendsburg-Eckernförde — 187 of 28,779 mapped." / "Since the previous sweep (1 day earlier): 13 postings opened, 13 closed." (spacing always stated - a 13-day-old previous sweep must never read as yesterday; `days_apart` added to churn evidence). Friendly copy: heading "At a glance", "open technology postings", "Last checked". No new statistics → **no methodology bump** (rendering change only). Runbook Block 0 gains the constraint-hygiene rule (check MEMORY §4 before refusing anything as "against the rules"). Commit `0650963`. | `make check` green (ruff, mypy, **459 pytest**, dbt PASS=202); `make release-check` green; `make live-site` green (12 sweeps, PASS=197); direct release checks live + `docs/index.html`: **0 problems**; friendly lines verified on the live page for both scopes with correct denominators |
| Usability protocol (Plan 1 Task 5) | 2026-09-04 | Complete; Iteration 11's study is prepared, pre-registered and **unrun** | `docs/usability-study-protocol.md` (commit `ef2f512`, tracked): five tasks against `docs/index.html` - German breadth line, the empty occupation ranking's meaning, per-country freshness, cross-country comparability (the real test: if participants compare the absolute counts anyway, that is a design finding routed to Plan 2, not a code patch), and what a closed posting means. Tasks written before any participant exists so they cannot be reshaped around what the page answers well; recruiting, running and write-up explicitly out of scope. | No gate applies (a document, no page output change); `git show --stat` verified the file is committed |


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

### 2026-09-03 - Increment 20, re-applied (corrective)

- **Why this note exists.** The 2026-09-01 entry above is accurate about intent and was left
  untouched, but the repository never carried its code. Verified before editing anything:
  `git log -- Makefile` stopped at `c9ade31`, an old collector commit, and `1a2b6be` - whose message
  says "record ... and increment 20" - touched only `.gitignore` and `SESSIONS.md`. The Makefile
  still globbed `data/raw/collections/jobtech/*/*/` in all three places. The edit was lost to a
  checkout or reset around the scraper-lab merge, and nothing was cherry-pickable. The record
  preceded the surviving edit; this note is the correction, not a rewrite.
- **What was re-applied.** Exactly the three globs, source segment only, depth unchanged:
  `LIVE_SWEEPS` (`Makefile:30`), and the two exported paths `OBSERVATIONS_PATH` and `MANIFESTS_PATH`
  (`Makefile:103-104`). `LIVE_READY` (`Makefile:31`) is byte-identical, so an empty wildcard still
  raises `no stored sweeps found` instead of publishing an empty page. The comment above
  `LIVE_SWEEPS` (`Makefile:24-29`) and the `live-site` block (`Makefile:91-102`) now say that every
  collector is read, why the depth is pinned at three segments, and that a second scope is expected
  to fail loudly rather than be summed.
- **Depth verified by counting, not by reading.** The depth-3 glob
  `data/raw/collections/*/*/*/manifest.json` resolves **9**; per source that is **8** `jobtech` plus
  **1** `ba`, which sums to 9, so the segment count after `data/raw/collections/` is unchanged. The
  depth-4 equivalent resolves **0**, so nothing nested can be double-counted. `make -n live-site`
  prints `publishing from 9 stored sweeps`, so make's own expansion agrees with the shell's. The
  2026-09-01 expectation of "8 before, 8 after" is stale - it was written when only `jobtech/` was on
  disk, and `ba/de-nuts3-panel/20260902T080422Z` has landed since.
- **Merge damage repaired in this file.** `SESSIONS.md` carried six committed conflict markers in two
  blocks - at the increment table and immediately before the 2026-08-31 scope note. In both blocks
  the `scrapers` side was empty and HEAD held all the content, so the six marker lines were deleted
  and nothing else. No recorded line was removed. It was the only tracked file with markers:
  `git grep -c -E "^(<<<<<<<|=======|>>>>>>>)" HEAD` reported `SESSIONS.md:6` and nothing else.
- **Gates, stated as run.** `make check` green before and after (ruff clean, mypy clean over 62
  source files, **459 pytest passed**, dbt `PASS=190 WARN=0 ERROR=0`), fully offline. No test and no
  `check` target was edited. `make release-check` was deliberately **not** run: it depends on `site`,
  not `live-site`, so it would have re-tested the synthetic sample and told us nothing about the
  widened glob.
- **The predicted failure was wrong, and the measured one matters more.** `make live-site` is red, as
  the 2026-09-01 note said it would be, but not where it said: it dies inside
  `dbt build --exclude tag:sample_fixture` with `PASS=183 ERROR=2`, so `scripts/publish.py` never
  starts and `_verify_single_scope` (`scripts/publish.py:756-772`) is never reached.
  **Increment 21 is therefore blocked behind two dbt failures, both of them the German panel meeting
  a pinned vocabulary for the first time.** Diagnosed against `data/dev.duckdb`, not guessed:
  - `accepted_values_mapping_quality_latest_mapping_method`: the `de-nuts3-panel` scope emits **six**
    methods absent from the list pinned at `transform/models/publish/schema.yml:153` -
    `not_available_ba_html` (occupation / `not_present`, 28,900 outcomes),
    `ba_city_municipality_nuts3` (22,575), `ba_city_qualifier_nuts3` (5,013),
    `ba_segment_provenance_nuts3` (839), `ba_city_municipality_ambiguous` (region / `ambiguous`, 297)
    and `ba_segment_disambiguated` (176). The pin behaved exactly as its comment
    (`schema.yml:151-152`) says it should: an unaudited vocabulary cannot be published silently. The
    fix is to extend the list deliberately, **never** to unpin it or lower its severity.
  - `not_null_dimension_demand_latest_value_label`: **12** German NUTS-3 codes reach the page with a
    null label, covering **839** postings - which is exactly the `ba_segment_provenance_nuts3` total,
    so the two are the same defect seen twice. When the region is attributed from the panel segment's
    own provenance rather than from the posting's city text, the collector wrote `nuts_code` and left
    `nuts_label` null, and `dimension_demand_latest.sql:38` publishes that null straight through from
    `stg_postings`. The codes are `DE937 DE403 DEB11 DE233 DE927 DEB35 DE273 DE943 DEE05 DEB3D DE938
    DEE0C`.
  - **The labels are recoverable in-repo, so this needs no re-sweep and no partition rewrite.**
    `data/reference/germany_plz_nuts_2024.csv` carries `nuts_code` and `nuts_label` over **all 400**
    distinct NUTS-3 codes from the destatis Anschriften source, and it resolves every one of the 12
    (e.g. `DE937` -> `Rotenburg (Wuemme)`, `DEB11` -> `Koblenz, Kreisfreie Stadt`). The published
    label is the Kreis name, not the panel's query seed - `DEF0B` publishes
    `Rendsburg-Eckernfoerde` where the panel seeded the town `Eckernfoerde`, and `DE408` publishes
    `Havelland` where the panel seeded `Brieselang` - so the backfill must join the reference, not
    `data/reference/ba_panel_nuts3.json`. Since `data/raw/` is immutable, the coalesce belongs in the
    transform or enrich layer.
- **Measured while diagnosing, for Increment 22.** The panel's postings map to **393** distinct
  NUTS-3 codes (381 labelled + 12 unlabelled) out of the 400-region frame. That is the count the
  German breadth line should state - a count, never a share - once the 12 labels are filled.
- **What this deliberately does not do.** No attempt to fix either dbt failure: extending a
  deliberately pinned vocabulary and backfilling a label join are data-model decisions with their own
  pinned tests, and folding them into a Makefile increment is how the 2026-09-01 edit got lost. No
  collector, model, publisher, test or data file was touched, and nothing under `data/` was written.

### 2026-09-03 - Increment 20b

- **What was measured before editing.** Both failures from the re-applied Increment 20 record,
  reproduced against `data/dev.duckdb` under the live `OBSERVATIONS_PATH`/`MANIFESTS_PATH` exports:
  `accepted_values_mapping_quality_latest_mapping_method` with **6** unlisted methods, and
  `not_null_dimension_demand_latest_value_label` with **12** null-label codes over **839** postings -
  exactly the `ba_segment_provenance_nuts3` total, so both failures were one defect seen twice.
  `stg_postings` carried 33,836 rows (28,900 BA + 4,936 jobtech) and the BA panel mapped **393**
  distinct NUTS-3 codes (381 labelled + 12 not), out of the 400-region frame.
- **The vocabulary admission, deliberate and cross-collector.** Ten BA values added to the
  `accepted_values` pin at `transform/models/publish/schema.yml` (now `:160`), the existing eight
  kept: six observed in the partition plus four **pre-registered from a source audit**, not from
  observed rows - `ba_segment_radius_nuts3` (`ba_jobsuche.py:1218`), `ba_plz_nuts3` (`:576`),
  `ba_plz_ambiguous` (`:581`) and `not_available` (the `RegionResolution` default, also `:396`,
  `:451`, `:506`, `:509`). Adding only the six observed would redden the build on any BA re-sweep
  that takes the PLZ or radius path. The other seven collectors' ~35 method literals are
  deliberately absent: no partition exists for them, so none may be collected. The pin's comment
  now records why the list grew, the observed-vs-audited split, and widens "a typo in
  `scripts/enrich.py`" to cover `scrapers/`. The pin itself was never lifted and its severity never
  lowered.
- **The label backfill, at the only layer that can change a stored partition's meaning.**
  `data/raw/` is immutable, so the fix is a new `transform/models/staging/stg_nuts_labels.sql`:
  one row per `nuts_code`, read from the **nine** reference CSVs that expose `nuts_code` +
  `nuts_label` (enumerated explicitly - a `*_nuts_2024.csv` glob silently misses
  `mpsv_obce_kraj_2024.csv` and `mpsv_okresy_kraj_2024.csv`; `union_by_name` because the German file
  carries two extra columns). `group by nuts_code` + `min(nuts_label)`, **not** `select distinct`:
  distinct over the pair would emit two rows for a code with two label spellings and fan out every
  posting count on join. Pinned by `contract: enforced: true`, `not_null` + `unique` on `nuts_code`
  and `not_null` on `nuts_label` in `transform/models/staging/schema.yml`. `stg_postings.sql:18`
  becomes `coalesce(cast(postings.nuts_label as varchar), labels.nuts_label)` on a **left** join -
  source row wins because the collected label is evidence and the reference is a backfill; left,
  never inner, so postings whose region is `not_present` (null `nuts_code`) keep their place in the
  denominator. The inner join to `stg_collection_manifests` is untouched. No dbt seed, no var, no
  snapshot - `read_csv` in a model, matching the project's constraints and `stg_postings`'s own
  inline `read_json`.
- **Conflicts surfaced, not hidden.** `min(nuts_label)` resolves a cross-file label conflict
  silently, which is exactly what the vocabulary pin exists to prevent, so
  `transform/tests/assert_nuts_label_unambiguous.sql` selects any code with two distinct non-null
  labels across the same nine files. Untagged on purpose: it runs under `make live-site` too. It
  passed on first run - no reference file pair currently disagrees.
- **Prevention at source (step 5, done rather than deferred).** `ba_jobsuche.py`'s two Tier-3
  `RegionResolution`s (`:1203-1220`) now take `nuts_label` from a new
  `GermanCrosswalk.label_for_nuts()` lookup over the same `germany_plz_nuts_2024.csv` the other
  tiers resolve from, so a future sweep stops producing code-without-label rows. The stored
  partition cannot change, which is why the staging backfill is required regardless. The pinned
  scraper tests took the change without a fight: all 51 BA tests and the full 459 passed unchanged,
  ruff and mypy clean.
- **Fan-out guard, checked explicitly as the highest-risk regression.** After the coalesce:
  `stg_postings` still **33,836** rows, BA region outcomes still sum to **28,900** (22,575 + 5,013 +
  839 + 297 + 176), BA region rows still **393** (the label completed existing `group by all` grains
  rather than splitting them), and `dimension_demand_latest` has **zero** rows with
  `dimension = 'region' and value_label is null`. All 12 spot-checked: `DE937` -> `Rotenburg
  (Wümme)`, `DEB11` -> `Koblenz, Kreisfreie Stadt`, `DE233` -> `Weiden i. d. Opf, Kreisfreie Stadt`,
  `DEE0C` -> `Salzlandkreis`. The published label is the reference Kreis name, not the panel's query
  seed, matching the 2026-09-03 Increment 20 finding.
- **Gates, stated as run.** `make check` fully offline and green: ruff clean, mypy clean over 62
  source files, **459 pytest passed**, dbt **PASS=195 WARN=0 ERROR=0** - PASS rose by exactly the
  five new resources (model + three contract tests + the singular test) and no test stopped being
  selected. The sample fixtures are unaffected: `accepted_values` rejects unexpected values, it does
  not require every listed value to appear, and the SE sample's labels are present so the coalesce
  is a no-op there. `make live-site` is red **exactly as planned**: dbt build completes
  (PASS=190 ERROR=0 excluding `tag:sample_fixture`), then `scripts/publish.py` raises
  `ValueError: 2 scopes have postings (ba/de-nuts3-panel, jobtech/jobtech-f5cf1d409aa51fad)` in
  `_verify_single_scope` (`publish.py:768`) - the failure Increment 20 originally predicted and
  Increment 21's actual job. `make release-check` deliberately not cited: it depends on `site`, not
  `live-site`, and re-tests only the synthetic sample.
- **No METHODOLOGY_VERSION bump.** The code-to-region assignment is unchanged; only presentation
  labels were completed and a vocabulary admitted. Increment 24's 1.3 -> 1.4 bump should mention
  this backfill. Nothing under `data/` was written, and the reference CSVs stay tracked in git
  (`git ls-files data/reference/`), so a fresh clone still builds.

### 2026-09-04 - Increment 21

- Implemented per `.kilo/plans/1788465051865-increment-21-per-scope-per-country-sections.md`,
  which supersedes Prompt 2's fixture-regeneration instruction: `data/sample/` was **not**
  regenerated (a second collecting scope in the committed sample would perturb the
  `tag:sample_fixture` dbt assertions and the exact-count pytest assertions for no gain), and the
  two-scope shape is covered instead by a hand-built DuckDB twin of
  `test_publish_builds_aggregate_page` (`tests/test_probe.py`, scopes `jobtech/jobtech-scope` SE
  and `ba/de-panel` DE) that runs inside `make check`, including `release_check.check_page == []`.
- **Governance before publisher, two commits.** `3f6f27d` amends `SOURCE_FEASIBILITY.md` by
  append: dated amendment (owner-relaxed ToS/robots gate for private research/educational use,
  2026-08-23), BA Jobsuche an active lane via `scrapers/ba_jobsuche.py`, the German data a
  **stratified region-bounded sample with a capped within-stratum draw over a frozen 400-region
  NUTS-3 panel - not a census, not a partial crawl**, the `Rejected` verdict superseded with its
  evidence intact, the German scope in Fixed Release Scope (source `ba`, scope `de-nuts3-panel`,
  country `DE`, sweep = one pass over the frozen panel, limitation = the manifest's own
  `coverage_limitations` string), and the Approval Gate For Germany left standing and recorded as
  **unmet** - no claim anywhere that BA approved anything.
- **Five scoped query paths, not three.** The old guard's docstring named
  `_query_dimension`/`_query_skills`/`_query_mapping`; the requirements query and the
  `_denominator` were pooling too (silent duplicate rows under a false "each Postings column sums
  to that sweep's posting count" claim). All now carry `(source, scope_id)`:
  `DIMENSION_LIMIT` applies **per scope** via `qualify row_number() over (partition by source,
  scope_id, dimension order by posting_count desc, value_label)`; `_query_mapping` groups by
  scope and keeps only the within-scope sum; `_query_requirements` keeps its `value_code`-last
  tiebreak; `_denominator` takes the scope key, keeps the `postings_total > 0` guard, and emits
  the "no coverage row" sentence for a scope without one. Published row shapes (`DimensionRow`,
  `MappingRow`, `RequirementRow`) are unchanged, preserving the renderers' index maths.
- **Per-scope subsections.** `_scope_keys` orders unique `(source, scope_id)` by demand (largest
  scope leads - on the live page that is `ba/de-nuts3-panel` at 28,900, then
  `jobtech/jobtech-f5cf1d409aa51fad` at 628), with one fallback subsection when demand is empty
  so the ranked tables and their denominators always exist (`release_check` fails a ranked table
  that disappears). `_scope_slug` makes stable unique table ids (`table-occupations-ranked-ba-de-
  nuts3-panel`). Countries: `h4` per scope under `h3 NUTS regions`, each with its own region
  denominator - the truncation went from harmless (25 of ~21 Swedish regions, no tail) to
  material (25 of 393 German regions), so the unlisted-tail sentence now matters. Occupations and
  Requirements: `h3` per scope, `h4` blocks per topic. The quality section's missing-mappings
  table is per scope as well - leaving it pooled would have summed across sources. New rows carry
  `data-source`/`data-country` so the existing filter script works unmodified; **no SCRIPT
  change**.
- **Insights per scope.** `insights.build` loops `_collecting_scopes` (demand order,
  `active_postings > 0`) and partitions the scoped rows before each rule call, so every rule
  keeps its signature and receives one scope's rows - which is what stops `_requirement_count`
  returning the first code match across scopes and the share totals summing both. The scope
  label renders as `<p class="label">source / scope_id</p>` beside each group in the Overview
  digest, Status and Survival - markup, never sentence text, because a scope id like
  `jobtech-f5cf1d409aa51fad` would read as an unsourced number to
  `test_insight_traceability_every_number_appears_in_the_source_rows`, which passes unmodified
  along with `test_insight_sentences_never_mention_a_second_scope`.
- **Release check by prefix.** `RANKED_TABLES` (exact ids) replaced by
  `RANKED_TABLE_PREFIXES` over `table-countries-regions`, `table-occupations-ranked`,
  `table-occupations-skills`: at least one table per prefix must exist, and every match needs its
  own consumed denominator sentence. `MASKED_TABLES` untouched - flows and survival are per-scope
  rows in one table with no region dimension. One addition the plan did not name:
  `https://www.arbeitsagentur.de/` joined `ALLOWED_URL_PREFIXES` (`release_check.py:20`), because
  the BA manifests cite it as `licence_reference` and the live page rendered it three times
  (countries, provenance, governance); registering the documented licence host is the same act
  that put `data.jobtechdev.se` there, and the page build still never requests it.
- **Guard removed last.** `_verify_single_scope` and its call deleted only after the sections,
  tests and release rules existed. The two refusal tests were replaced one-for-one:
  `test_publish_renders_each_scope_in_its_own_sections` (two subsections per panel, no pooled
  figure, per-scope denominators, per-scope `DIMENSION_LIMIT` with the unlisted tail, requirement
  columns summing to their own scope, labelled digest, unique ids, `check_page == []`) and
  `test_insight_build_states_each_scope_separately` (one sentence per scope per rule, correct
  `Insight.scope`, no scope id in text, zero-posting scope silent). Test count stays **459**.
- **Deliberately not done.** No METHODOLOGY_VERSION bump (Increment 24), no breadth line or
  coverage percentage (Increment 22 - the denominator must come from
  `data/reference/geography_nuts_2024.csv`, not a hardcoded 400), no German occupation mapping
  (Increment 23), no `data/sample/` regeneration, nothing written under `data/raw/`, no new
  dependency and no network at build time. The Status section's cross-scope "row(s) stored by
  the latest sweep of each scope" storage stat was left standing on purpose: it was already
  cross-scope in the single-source fixture (20 = 11 + 9), it counts stored rows rather than
  postings, and its sentence says what it is; changing it was not in this increment's scope.
- **Gates, stated as run.** `make check` fully offline and green: ruff clean, mypy clean over 62
  source files, **459 pytest passed**, dbt **PASS=195 WARN=0 ERROR=0** (no dbt resource added or
  removed). `make live-site` **green for the first time on two scopes**: `publishing from 9
  stored sweeps`, dbt PASS=190 ERROR=0, `wrote site\build\index.html (2 rows)`. Live-page release
  check run directly as `uv run --offline python -m scripts.release_check site/build/index.html`
  (not `make release-check`, which rebuilds the synthetic page over the live one): **0
  problems**. `make release-check` then run separately, green on the synthetic page (0 problems).
  Spot-check of the live page: DE region subsection lists 25 regions with "Ranked from 28,603
  mapped posting(s) of 28,900 in the latest sweep; 28,900 carry a structured region. Only the 25
  most frequent regions are listed below, accounting for 2,729 of those mapped postings; the
  rest sit in an unlisted tail."; DE occupation and skill rankings empty with "Ranked from 0
  mapped posting(s) of 28,900 ... 0 carry a structured occupation/skill" (Increment 23's job,
  not a defect); SE rankings and denominators name their own 628-posting sweep; the Overview
  digest labels each scope's group; no demand figure on the page is the sum of both scopes.
- **Acceptance criterion 2 is now met**: the page renders all countries, each in its own
  per-country/per-scope section. Remaining against the finish line: criterion 3 (breadth line,
  Increment 22), criterion 4 (two more sister-lab sweeps for `ba/de-nuts3-panel` - data
  collection, not code), criterion 5 (German occupation mapping, Increment 23).

### 2026-09-04 - Increments 22, 24 and the cancellation of 23

- **Rule suspension, recorded not broken.** The one-increment-per-session rule in
  `SESSION_RUNBOOK.md:40-52` was suspended for this session by the project owner's decision: the
  rule exists to stop two agents colliding in `publish.py` and `SESSIONS.md`, which is not the
  situation, and finishing 22/23/24 one per session was costing three more plan-and-record
  cycles for roughly three hours of work. It is not licence to widen scope: nothing outside the
  three increments and the artefact was touched. Four commits, in task order, each verified with
  `git show --stat HEAD`: `ef3f65a` (22), `12412d0` (23), `8db030a` (24), `2a4e537` (artefact).
- **Increment 22 - the breadth view's design.** Breadth comes from a dbt publish view, not a CSV
  read in the publisher (decision 1: every `_query_*` is a DuckDB query against the publish
  layer; 20b set the precedent of joining pinned references inside dbt via `stg_nuts_labels`).
  `region_breadth_latest` takes `count(distinct value_uri)` from `dimension_demand_latest`
  region rows - the same rows `_query_dimension` truncates at 25 - and left-joins the frame
  (five-character NUTS codes in `stg_nuts_labels`, grouped by country prefix), so the frame is
  the union of all nine reference CSVs, never the Sweden-only `geography_nuts_2024.csv`. The
  publisher renders the breadth line, then the manifest's own `coverage_limitations` string
  verbatim (decision 3: page and manifest cannot drift), then the existing `_denominator`
  paragraph and the table. All three paragraphs before the table use `class="definition"`:
  `release_check.py:155-156` captures a `class="denominator"` paragraph for the next table, so
  anything with that class between the denominator and its table would be consumed instead.
  A null frame renders "No NUTS-3 frame is pinned ... so no breadth count is published.",
  never "N of 0", and no percentage exists in the line or the fixtures (decision 2).
  **Cross-check on live data: `regions_with_postings = 393` for `ba/de-nuts3-panel`, the figure
  20b measured; the view is right and the note is right.** SE is 21 of 21.
- **Increment 23 - cancelled, not deferred, on three citations.** `scrapers/ba_jobsuche.py:51-52`
  (the BA search page carries only a free-text title, no occupation code, so the collector sets
  `occupation_mapping_status=not_present` by design), `scrapers/ba_jobsuche.py:1222-1246`
  (`NormalizedRecord` is built with `esco_occupation_uri=None`,
  `occupation_mapping_method="not_available_ba_html"` - no occupation input is carried at all, so
  there is nothing in the stored partition to map), `scripts/sanitize.py:31-35` (the allowlist
  carries only the occupation mapping outputs; no title field, and the published methodology
  states "job titles and free text are never classified", a public commitment). No title
  classification, no detail-page re-sweep, no synthetic German occupations. The replacement is
  `_empty_by_construction`: one sentence in any scope whose `mapping_coverage_latest` row reports
  `postings_with_source_value = 0` with `postings_total > 0`, for occupation and skill alike,
  derived from the data alone so any future source with the same gap is described correctly.
  Acceptance criterion 5 is unachievable from this source - it was written when Germany was
  expected through HR-BA-XML, which would have carried occupation codes. Revival conditions
  recorded in the roadmap: a source that publishes a structured occupation field, or an
  evaluated title-classification method (ruled out).
- **Increment 24 - what was deliberately not touched.** `scripts/collect.py:55-63` limitation
  constants: Task 0's scoped grep over `tests/` and `transform/` found the only pins
  (`tests/test_probe.py:884`, `:1047`) compare runtime collector manifests to the `collect.*`
  symbols, not the committed sample, and the constants' text describes the Swedish keyword and
  field scopes, which is not false - so the constants stay, no `make sample` regeneration, no
  re-run of the whole gate (decision 5, and increment 21's avoidance preserved). No edits at the
  interpolation sites (`publish.py:1087`, `:1911`, `:1932` now shifted by the new text,
  `release_check.py:369-372`): they interpolate the constant; the CSV-filename test and the
  release version rule were confirmed to move with it. `METHODOLOGY_VERSION` and its test pin
  moved in the same commit, as the roadmap demands.
- **The artefact fix.** `site/build/` is gitignored (`.gitignore:59`) and `make release-check`
  depends on `site` (`Makefile:63`), which rebuilds from the synthetic sample and so destroyed
  the live page every session - the reason the project felt stalled with nothing to show. Fixed
  by committing `docs/index.html` (not gitignored) as a copy of the live page: footer reads
  "built from stored collection partitions", headline carries the German 28,900, breadth line
  reads "393 of 400 DE NUTS-3 regions have at least one mapped posting." with the panel
  manifest's caveat under it, the DE occupation and skill blocks carry the
  empty-by-construction sentence, and methodology 1.4 is stamped in the footer, the
  `data-methodology-version` attribute and every CSV filename. `uv run --offline python -m
  scripts.release_check docs/index.html`: 0 problems. `SESSION_RUNBOOK.md` section 3 now carries
  the ordering rule with its one-line reason: finish with `make live-site`, never `make
  release-check`.
- **Gates, as run and with their actual numbers.** Baseline before editing: `make check` green
  (ruff, mypy 62 files, 459 pytest, dbt PASS=195 WARN=0 ERROR=0). After: `make check` green
  (ruff, mypy 62 files, **459 pytest** - the new assertions extend existing tests rather than
  adding files - dbt **PASS=201** WARN=0 ERROR=0, +1 view model and +6 tests over the 195).
  `make release-check` green on the synthetic page (0 problems), run **before** the live build
  so it could not destroy the live page. `make live-site` green: `publishing from 9 stored
  sweeps`, dbt PASS=196 ERROR=0 (190 + the new model and its untagged tests), `wrote
  site\build\index.html (2 rows)`. Direct release check on the live page: 0 problems; on the
  `docs/index.html` copy: 0 problems. No `%` anywhere new; no figure on the page equals the sum
  of the two scopes; the Status section's pre-existing cross-scope stored-rows stat left
  standing as recorded on 2026-09-04.
- **Acceptance after this session:** #1 green, #2 met (Increment 21), #3 met and published
  (393 of 400), #4 still 1 of 3 sweeps - sister-lab data collection, not code, #5 unachievable
  from this source (recorded, with the page stating the gap). Recommended next step: none -
  finish line reached; Increment 25 only if the live-service budget is approved.

### 2026-09-04 - Sweeps restart (Plan 1 Task 1)

- **What was true before this session, measured.** The Swedish scope had been idle for 11 days
  after eight sweeps (latest 2026-08-22T20:12Z, 308.5 h against a 48 h threshold), so both
  published scopes carried stale badges; `ba/de-nuts3-panel` was 64.7 h against 24 h. The daily
  flow buckets were 08-19, 08-20, 08-22 - the 08-21 bucket is missing and nothing existed after
  08-22. Source: `posting_flows` at day grain, `source_coverage` freshness on the latest sweep
  per scope.
- **Preflight, no writes.** Working tree clean at `563f434` on `merge/scrapers-lab`.
  `.env` present and carries `OBSERVATORY_HMAC_KEY` (presence checked, value never read or
  printed) - a missing key would not fail loudly, because `Makefile:12` conditions the flag on
  the file's existence and would run the collector keyless. The key was **not** rotated, so
  `assert_key_rotation_does_not_close.sql` stays silent and posting pseudonyms are continuous.
  Baseline `make check` green: 459 pytest, dbt PASS=201 WARN=0 ERROR=0.
- **The sweep.** `make sweep` from the main checkout (never a worktree, `Makefile:66`): sweep
  complete at `jobtech/jobtech-f5cf1d409aa51fad/20260904T183925Z-f5cf1d409aa5`, 623 rows over 7
  pages. Verified exactly one new partition (8 -> 9 under the scope, `ba` still 1, total 10 with
  the German panel), directory name in `YYYYMMDDTHHMMSSZ` form, and nothing existing changed -
  `git status --porcelain` empty after, `data/raw/` append-only honoured.
- **The 2026-08-21 hole is permanent, on the record.** Posting observations are collected only
  in the present and `data/raw/` is immutable, so 08-21 can never be filled. The gap keeps
  `rule_trend` silent until the rule's reading window has moved entirely past it
  (`scripts/insights.py` gates on `TREND_MIN_SWEEPS = 14`, `TREND_MIN_SPAN_DAYS = 7`, and
  refuses a gap adjacent to the newest bucket - so 14 sweeps is necessary, not sufficient). No
  synthetic bucket, no widened rule: the hole is a true statement about the data. Grow past it.
- **Gates, in the runbook's order.** `make release-check` green on the synthetic page first
  (0 problems, dbt PASS=201); `make live-site` last: `publishing from 10 stored sweeps`, dbt
  PASS=196 ERROR=0, `wrote site\build\index.html (2 rows)`; direct release check on the live
  page (`uv run --offline python -m scripts.release_check site/build/index.html`): 0 problems.
- **What the page now says.** The Swedish scope is **Fresh** again: SE jobtech observed
  2026-09-04 18:39 UTC, 623 postings, status Fresh/Covered; the digest line reads
  "1 fresh" of 2 source scopes. The German panel stays honestly **Stale** (67 h against its
  24 h threshold) pending the sister lab's sweeps - that is Task 2, not this repo's to fix.
  `docs/index.html` refreshed from the live build, re-checked directly (0 problems), committed
  as `541e47c` (5 lines: the two scope rows' observed-at/status, the digest count, the build
  stamp, the footer). `site/build/` stays ignored and ephemeral.
- **Cadence, pre-registered and not relaxed.** Never slower than every two days; the design
  target is twice daily (14 sweeps over 7 days, the trend rule's shape; the observed median
  interval on the existing sweeps is 4.0 h). This session contributed sweep 9; future sessions
  in the plan's cadence add the rest. Task 1's stop condition - `fresh` plus four consecutive
  daily buckets with no gap adjacent to the newest - is not yet met after one sweep: the newest
  buckets are 08-22 then 09-04, an 11-day hole, which only continued sweeping can grow past.
- **Task 2, asked for and not started.** Two further complete sister-lab sweeps over the same
  frozen 400-region NUTS-3 panel (`ba/de-nuts3-panel`), same partition shape
  (`observations.ndjson` + `manifest.json`), unchanged HMAC key version, `YYYYMMDDTHHMMSSZ`
  directory names, with each sweep's own `coverage_limitations` string recorded before it
  lands. This repo only asks, verifies and publishes; it does not collect German data.
- **Deliberately not done.** No threshold, gate constant or test edited; nothing under
  `data/raw/` written besides the one new partition; no `make sample` regeneration; no trend
  sentence forced (the rule stays silent, correctly); Increment 25 untouched; no German
  survival figure stated from one sweep. `make check` was not re-run after the sweep: the sweep
  added data only, no code changed, and `live-site`'s dbt run (PASS=196) is the gate that
  exercises the live partitions.

### 2026-09-04 - German panel sweeps 2 and 3 (Plan 1 Task 2)

- **The co-ordination premise dissolved.** The plan asked for "two further complete passes from
  the sister lab". After the `merge/scrapers-lab` merge the sister lab's collector, pinned panel
  and DoD gate all live in this checkout: `main.py --source ba --panel --date <ISO>` drives
  `BAJobsucheCollector` in panel mode (`scrapers/ba_jobsuche.py` `_fetch_panel`, which walks the
  pinned `data/reference/ba_panel_nuts3.json`), `PANEL_HANDOVER.md` §3 is the sweep runbook
  (gate first, sweep to a log, tail only, then the acceptance check), and
  `scripts/check_ba_panel_readiness.py` asserts the step-2b DoD across every stored partition.
  The request became a run, with the runbook's discipline kept: sweeps logged to
  `logs/ba-panel-sweep*.log` (gitignored output, read as tail only), never streamed into the
  session. The first background attempt was orphaned by a background-process lifetime bug
  (24 lines of log, no partition, process gone - recorded here because a silent re-run could
  have double-counted); the retry completed cleanly. No partition was written by the dead run:
  `data/raw/collections/ba/de-nuts3-panel/` held exactly one directory before the retry
  finished.
- **Sweep 2, as measured.** `20260904T201534Z` (observed_at 2026-09-04): 400 region queries,
  398 with >=1 row, 2 empty (`DE231` - its `wo=92211` anchor returns `UNGUELTIG` mode, as in
  sweep 1; and `DEB24` - Beinhausen advertised 1 posting in sweep 1, 0 now: a genuine closure),
  273 regions at the declared 4-page cap, 1321/1321 planned pages, 0 failed pages, 29 absorbed
  403 throttles, 2028 HMAC duplicates dropped, **29,068 rows**. Manifest identity holds:
  `status=complete`, `expected_rows == row_count == NDJSON lines`, `scope_hash` and
  `hmac_key_version v1` unchanged, directory name in `YYYYMMDDTHHMMSSZ` form, partition shape
  `ba/de-nuts3-panel/<sweep_id>/` with the third file `panel_regions.json` beside
  `observations.ndjson` + `manifest.json`.
- **Sweep 3, as measured.** `20260904T210722Z` (observed_at 2026-09-05, so the panel now spans
  three distinct days): byte-for-byte the same shape - 400/398/1321/0-failed, 29,068 rows,
  273 capped, 48 throttles. Run ~50 min after sweep 2 under the same key; the two sweeps are
  deliberately close in wall-clock, which matters for how their closure signal reads (below).
- **The plan's §3.2 cross-checks, all four, measured.**
  1. Partition shape: three segments after `data/raw/collections/`, `manifest.json` present -
     `make live-site`'s depth-pinned glob counts them (10 -> 11 -> 12 stored sweeps).
  2. `make live-site` dbt green with no fifth unpinned BA method value (PASS=196 ERROR=0 both
     times): sweeps 2 and 3 carry the same `ba_segment_provenance_nuts3` mapped /
     Tier-1-ambiguous vocabulary as sweep 1, so the 20b pin held and nothing was added to
     `schema.yml`.
  3. Breadth: `region_breadth_latest` reads **392 of 400** for the latest sweep (sweep 1 was
     393; `DEB24` lost its single posting - a real closure, not a panel change: the membership
     hash and all 400 queries are unchanged). The plan's guard band was "stays in the same
     region as 393 of 400"; 392 is one closure away, not a collapse, and the panel DoD's
     >= 390 bar passes. Recorded as a change in the published number, not an anomaly.
     `assert_nuts_frame_counts` green at 400 DE / 21 SE (frame unmoved, denominator safe).
  4. Region outcomes sum to each sweep's posting count: sweep 1 28,603 mapped + 297 ambiguous
     = 28,900; sweeps 2 and 3 28,779 + 289 = 29,068 each. `complete_sweeps` incremented by
     exactly one per delivered sweep: 1 -> 2 -> 3 for `ba/de-nuts3-panel`
     (`collection_frequency`), median interval 36 h over the three.
- **The panel DoD gate, as run.** `uv run --offline python scripts/check_ba_panel_readiness.py`
  after each sweep: all six PASS lines across ALL partitions - manifest reconciliation (3/3),
  breadth (>= 390 of 400 per sweep, union 393), frozen-panel integrity (one membership hash
  `545b162ec6e5fbdc...` across all 3 sweeps, equal to the pinned definition), zero failed
  requests (77 absorbed 403 throttle events total - throttle events, not failures), PII scan
  clean across 87,036 rows, cap-as-scope honesty (page cap 4 in `scope_json` and
  `coverage_limitations` for every sweep).
- **What the page now says.** Both scopes **Fresh** and covered: DE ba 29,068 postings observed
  2026-09-05, SE jobtech 623 observed 2026-09-04; the Status digest reads "2 of 2 source
  scope(s) covered · 2 fresh". `collection_frequency.complete_sweeps = 3` - acceptance
  criterion 4 **met**, marked in `FUNCTIONALITY_ROADMAP.md`. `docs/index.html` refreshed from
  live builds and committed per sweep (`e25a94d` after sweep 2, `9bd4563` after sweep 3);
  direct release checks 0 problems each time.
- **German survival, stated honestly per §3.3.** The page's DE survival sentence now exists
  (median observed duration 2.0 days across 12,068 closed postings) because three sweeps
  technically exist - but sweeps 2 and 3 are ~50 minutes apart, not spaced, so the closure
  signal is one real epoch (09-02 -> 09-04) plus one near-instantaneous re-observation that
  contributed 13 closures. **Do not read 2.0 days as a German posting lifetime**: with a 48 h
  first interval and a ~1 h second, closures are inferred at wildly different resolutions and
  the median is resolution-dominated. The plan's own warning ("closure is inferred from
  absence at the next complete sweep") is restated here: the survival series becomes readable
  only under a spaced cadence (weekly per `PANEL_HANDOVER.md` §3 cadence, daily at most). No
  duration figure was fabricated, no threshold moved.
- **What arriving sweeps did not change.** Increment 23 stays cancelled: sweeps 2 and 3 confirm
  the occupation gap empirically - 0 postings carry a structured occupation value in any of the
  three German sweeps, and the empty-by-construction sentences still render. No German trend
  or duration claim beyond the caveated survival sentence; no new scope; no census.
- **Deliberately not done.** No `data/raw/` rewrite (append-only: 3 German partitions now,
  nothing touched from sweep 1); no `make sample` regeneration; no threshold, gate constant,
  test or Makefile edit; `make check` not re-run between the sweeps (no code changed;
  `live-site`'s dbt PASS=196 exercised the live partitions both times); Increment 25
  untouched. `logs/` is gitignored run output, not committed.

### 2026-09-04 - Tasks 3, 4 and 5 (Plan 1 close-out)

- **Session rule, recorded not broken.** The owner's instruction "carry out the remaining
  tasks in order, one at a time" overrides the one-increment-per-session rule for this
  session, as the 2026-09-04 wrap-up did: the tasks are operations and one small test, none
  of them collides in `publish.py`/`SESSIONS.md` the way two code increments would, and each
  was still done, verified and recorded as its own unit with its own commit.
- **Task 3 - the cadence guard, one honest test.** `transform/tests/assert_cadence_not_abandoned.sql`
  (untagged, so it runs under `make check` AND `live-site`): a scope fails when its latest
  complete sweep is older than **4x** its own `freshness_threshold_hours`, measured against
  the same `OBSERVATORY_REFERENCE_TIME` the rest of the project reads (`source_coverage`'s
  env_var with the sample's pinned 2026-08-15T12:00:00Z default), so it is deterministic
  offline. Why 4x: on the committed sample the largest threshold multiple is the deliberately
  stale keyword scope at 171/48 = **3.6x**, so 4x is green on the sample by measurement, not
  by luck; on the measured 2026-09-04 pre-restart state, the abandoned Swedish scope sat at
  308.5/48 = **6.4x** (the test would have fired - eleven days of silence would have been a
  red gate instead of a badge only a human reader notices) while the German panel's 64.7/24 =
  **2.7x** ordinary staleness would not have fired. That split is the whole design:
  abandonment is a gate, staleness is a badge. Verified: `make check` dbt PASS=202 (+1),
  `live-site` dbt PASS=197 (the untagged test runs there too), release checks 0 problems.
  Deliberately absent: scheduler, notification channel, new dependency, any Makefile edit. If
  the test ever reddens `make check` on the sample, the sample changed - investigate the
  sample, never the multiple.
- **Task 4 - the trend rule, verified not forced.** All four preconditions of `rule_trend`
  (`scripts/insights.py:359-412`), measured per scope after all of this session's sweeps:
  - `jobtech-f5cf1d409aa51fad`: `complete_sweeps = 9` (**< 14**, unmet); span 16 d (>= 7, met);
    newest daily buckets 08-22 -> 09-04 (**13-day gap adjacent to the newest**, unmet - the
    pre-registered no-gap precondition fails, and the permanent 08-21 hole is still inside the
    rule's reading window besides); two comparable buckets exist (met).
  - `ba/de-nuts3-panel`: `complete_sweeps = 3` (**< 14**, unmet); span 3 d (**< 7**, unmet);
    newest buckets 09-04 -> 09-05 are adjacent (met); buckets exist (met).
  `rule_trend` re-run directly from `scripts.insights` against the live `posting_flows` /
  `collection_frequency` rows: **SILENT for both scopes** - the pre-registered behaviour,
  not a bug. `TREND_MIN_SWEEPS`, `TREND_MIN_SPAN_DAYS` and the no-gap precondition untouched.
  The rule becomes evaluable for Sweden once the restarted cadence holds (9 of 14 sweeps,
  and the window must grow past both the 08-21 hole and the 08-22->09-04 gap). Note the
  page's separate "Trend direction Daily rising within the source (28,900 to 29,068)" stat is
  `publish.py`'s own scope-internal direction arrow from the flow series - not `rule_trend`,
  which is the pre-registered N=14/M=7-day gated sentence and stays silent.
- **Task 5 - the usability protocol, prepared only.** `docs/usability-study-protocol.md`
  (new, git-tracked): five think-aloud tasks against `docs/index.html` for >= 5 students or
  recent graduates - find the German breadth line (392 of 400); explain the empty occupation
  ranking (empty by construction, not "no jobs"); find each country's data time; the
  comparability question (the real test: comparing 623 with 29,068 anyway is a **design
  finding routed to Plan 2**, never patched into the page now); and what a closed posting
  means (inferred from absence). Tasks pre-registered before any participant exists; per-task
  failure modes named so findings have somewhere to land; recruiting, running and write-up
  explicitly out of scope; no page change from imagined findings.
- **Gates for the session, as run.** `make check` green (ruff, mypy 62 files, 459 pytest,
  dbt **PASS=202** WARN=0 ERROR=0, +1 test for the cadence guard); `make live-site` green
  (12 stored sweeps, dbt PASS=197 ERROR=0, 2 rows); direct release checks on the live page
  and on `docs/index.html`: 0 problems each. `scripts.check_ba_panel_readiness` green across
  all 3 German partitions (six PASS lines).
- **Commits this session, in task order:** `e25a94d` (artefact, sweep 2), `9bd4563`
  (artefact, sweep 3), `61e816f` (SESSIONS record for Task 2), `f8a8425` (cadence guard),
  `7db0381` (artefact re-sync), `ef2f512` (usability protocol).
- **Deliberately not done.** No threshold, gate constant, test or Makefile edited to turn
  anything green; no backfill of the 08-21 bucket or the 08-22->09-04 gap; no forced trend
  sentence; no German survival figure stated as a lifetime (the 2.0-day median is
  resolution-dominated by the unspaced second interval, recorded in the Task 2 note); no
  recruiting; Increment 25 and any new source untouched.

### 2026-09-05 - Uniform inferences and the instrument-board redesign

- **Owner decisions, recorded before work started.**
  1. **The no-new-dependency rule is lifted** (MEMORY.md §5, SESSION_RUNBOOK Block 0,
     amended this session): presentation libraries and premade assets are allowed for speed
     and beauty. What stays: `make check` fully offline (that is the API-quota firewall,
     not a dependency rule) and the release check's no-external-asset scan - the sanctioned
     path for a JS chart library is Increment 15's existing spec: vendor it **inline**,
     pinned, licence-attributed, with the server-rendered SVG staying as the accessible
     representation. Nothing was vendored in this session because the redesign needed none:
     every new figure is server-rendered inline SVG from Python string templates.
  2. **No occupation-type inferences at all.** The owner asked whether roles/skills/education
     guidance could be inferred; answer: SE yes, DE never (no occupation field), education
     never (no field, and title classification is the cancelled increment). The owner chose
     uniformity over a Swedish-only feature: "we don't have the types of roles for germany?
     then i don't want to add that for sweden either, app should stay uniform. Just stick to
     what is being done currently."
- **The two uniform rules, both statistical and both per-scope.** Added to
  `scripts/insights.py` under the existing traceability law (every numeric token must appear
  in the source rows; silence beats hedging; no cross-scope sentence):
  - `rule_region_concentration(regions, mapping_coverage, scope)` - "The leading region is
    X, with N of M mapped posting(s) in this sweep." M comes from `mapping_coverage_latest`
    (region dimension), **never** from summing the rendered ranking: the ranking truncates at
    DIMENSION_LIMIT=25, so its column sums to the listed top-N (2,729 for DE), not the sweep
    (28,779). The first implementation made exactly that mistake and was caught by reading
    the built page: "187 of 2,729" -> corrected to "187 of 28,779". Preconditions: a region
    coverage row with mapped > 0, >= 2 mapped region rows, a unique leader (no tie).
  - `rule_sweep_churn(flows, scope)` - "Between the two most recent daily buckets (N days
    apart), X posting(s) opened and Y closed, leaving Z active." Reads `posting_flows`' own
    numbers; the bucket spacing is stated because the DE buckets are 09-04 -> 09-05 (one
    day) while SE's newest pair spans a 13-day hole - churn claims no direction, so no
    cadence gate applies (unlike `rule_trend`, which stays silent and untouched). Masked
    buckets (null counts) silence the rule.
  - Both wired through `insights.build(..., regions=())` (new optional parameter,
    backward-compatible) into the `countries` and `survival` sections and the Overview
    digest; `_render_countries` gained section-insight rendering for the concentration
    sentence beside its scope's plate.
- **Methodology 1.5.** Both new sentences are definitions in the 1.3 sense (rules deciding
  when a number is stated and against which denominator), so the version bumped with the
  change, the test pin moved in the same commit (`tests/test_probe.py`
  `test_methodology_version_covers_the_requirement_dimensions`), README 1.4 -> 1.5,
  USER_MANUAL's CSV example `...-methodology-1-5.csv`. The 1.5 comment block in
  `scripts/publish.py` states what changed and why it cannot share a version with 1.4 pages.
- **The redesign, implemented from the reviewed spec.** `design/UI_REDESIGN_SPEC.md` (811
  lines, guideline-reviewed 2026-09-04 with findings resolved) + `design/prototype/index.html`
  were already in the checkout untracked; this session ported them into `scripts/publish.py`
  and committed both (spec `f126600`, implementation `3bbf640`):
  - **STYLE replaced wholesale**: spec §1.2 palette (housing/signal/caution/ink/ground + state
    tones + hatch + unknown), §1.3 type voices (Data Register monospace for all numerals and
    the h1, Panel Label for headers/eyebrows, body at 16/1.5), plate borders 1.5px, amber
    focus with ink ring, `theme-color` meta, `touch-action: manipulation`, mobile ladder.
  - **Observation board** (§3.3): one card per scope - h3 scope name with `translate="no"`,
    country chip, both lamps, mono count readout ("active postings · this scope only"),
    observed time, frame strip, trend line (per-scope `_finest_series` + `_direction` +
    complete-sweep count, replacing the single leading-scope pick). The **"Largest single
    observation" stat is removed** (spec §1.8 item 1: it invited the forbidden cross-scope
    comparison); stats are now Last update + Source coverage.
  - **Annunciator lamps** (§3.2): `_lamp`/`_lamp_freshness`/`_lamp_coverage` - bulb + Panel
    Label text + both numbers ("Fresh · 13 h old · threshold 24 h", "Covered · 29,068 of
    29,068 rows"); `_badge` now emits the same lamps in every status cell (24 on the live
    page). Unknown states render the unknown pair rather than crashing on a missing row.
  - **Frame strips** (§1.5/§3.4): `_frame_strip` - <= 60 regions: one `<rect>` per tick; the
    DE 400-frame: two pattern-filled runs at 4px/region with graduations every 100;
    `aria-label` + `<title>` + `<desc>` carry the breadth sentence. Pattern ids carry a
    context suffix (`-card`/`-regions`) because the live release check caught duplicate ids
    when one scope's strip rendered in two places - fixed and re-gated, not suppressed.
  - **Scope plates** (§3.1): `_scope_plate` wraps Countries' region blocks, Occupations'
    rankings, and Requirements' distributions - name as a real h3 (heading ladder intact),
    country chip, lamps. Countries' old h4 subsection headers are gone.
  - **Absence plates** (§3.9): the five empty German surfaces (occupation ranking, skill
    ranking, employment type, working hours, contract duration) now render dashed plates with
    a typed eyebrow + sentence + the drawn-from denominator line (rankings) instead of empty
    tables. Occupation/skill condition stays `mapping_coverage_latest`
    (`postings_with_source_value = 0`, `postings_total > 0`); the three requirement
    dimensions use spec Flag 1 option (b): no rows for the dimension + a positive sweep
    total. The release check's ranked-prefix rule still holds because the Swedish scope
    renders every prefix (and its absence is the point: a scope that cannot feed a ranking
    shows a typed state, not a dead table).
  - **Mapping chips** (§3.7): `_mapping_chip` beside each Swedish ranking - three segments
    (mapped filled / carries-but-unmapped hatched / no-field hollow) scaled within
    `postings_total`, printed counts, aria-label repeating the denominator's numbers.
  - **Mark key** (§3.5) in Overview: filled/hollow/hatched/dashed with one sentence each.
  - **Suppressed cells** (§3.10): `td.suppressed` hatched ground on the word; survival and
    flow cells carry `_suppressed_class`. **Requirement markers** (§3.11): hollow dot before
    `Not stated`, hatched swatch before `Unrecognised code`.
- **Tests.** `_rich_rows` gained region rows + a region coverage row + two daily flow rows;
  the main publish test now pins the churn sentence (7 insight paragraphs: the digest
  double-renders latest + both rankings + churn), concentration silence with one mapped
  region, and the new absence-plate/markup assertions; the two-scope test pins the plate h3s,
  `translate="no"`, the two occupation/skill absence plates with their ranked tables absent
  for the German scope, and the requirement-table sums unchanged; unmet-precondition cases
  cover solo/tied/no-coverage-region and churn's one-bucket/masked cases. One corruption
  during editing (`reqs` fixture) was caught by the suite and fixed. Full gate: ruff clean,
  mypy clean 62 files, **459 pytest**, dbt **PASS=202**; `make release-check` green on the
  synthetic page; `make live-site` green (12 sweeps, PASS=197); direct release checks on the
  live page and `docs/index.html`: **0 problems**. Live verification: 2 board cards, 6
  scope plates, 5 absence plates, 4 frame strips, 2 mapping chips, 24 lamps; both new
  sentences firing with correct denominators.
- **What was deliberately NOT inferred.** No occupation or skill ranking was added for
  Germany (impossible) or kept for Sweden as a special case (owner chose uniformity); no
  education statement (no field anywhere); no trend claim (the pre-registered 14-sweep gate
  stands, 9 of 14); no German lifetime reading (the 2.0-day median stays caveated); no DE-vs-SE
  comparison; no new ratio or percentage anywhere (counts only, as ever).
- **Commits:** `3bbf640` (rules + redesign + tests, one atomic change because the tests pin
  both), `f126600` (design spec/prototype/screenshots), `69bdf1e` (published artefact).
- **Open follow-ups from this session:** tile-grid map and vendored-uPlot interactivity
  (Increment 15's spec, now unblocked by the lifted rule) are NOT done - the board's strips
  and sparklines are the charts so far; the IA consolidation to five sections (proposed in
  the 2026-09-05 chat summary) is NOT done - all nine sections and slugs stand.

