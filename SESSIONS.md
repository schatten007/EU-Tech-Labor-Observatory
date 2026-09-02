# Scrapers Lab Sessions

Lab session log. The main project's session history was removed on purpose:
it recorded feasibility decisions (single Sweden source, no German collection)
that this lab does not inherit. From this point the log covers only scraper lab
work.

Keep each increment in one session. Unfinished work moves to the next row rather
than expanding the active increment.

| Increment | Session | Status | Scope | Check |
| --- | --- | --- | --- | --- |
| L0 | 2026-08-20 | Complete | Sterilize the worktree context: remove SOURCE_FEASIBILITY.md and main-project session history; add SCRAPERS.md charter, SCRAPER_FEASIBILITY.md checklist, lab Makefile, and scraper deps. | `make check` passed |
| 1 | 2026-08-21 | Complete | CBOP/ePraca (PL): Collector Interface + writers, robots/pacing, retry/backoff, HMAC sanitize, PolandCollector, SchemaValidator, CLI + `make scrape`; feasibility gate; live canary and full DoD sweep. | `make check` passed (69 tests); full sweep complete |
| 2 | 2026-08-22 | Complete | Úřad práce / MPSV (CZ): planning (feasibility gate green, live probe, written plan) **and** implementation — MPSVCollector, codelist->NUTS 2024 crosswalk reference, HMAC-only delta reconciliation, CLI + Makefile wiring, tests. | `make check` passed (113 tests); two consecutive daily sweeps complete |
| 3 | 2026-08-22 | Complete | Adzuna (DE + NL, multi-country adapter): feasibility gate (robots + ToS + live contract probe), `AdzunaCollector` + `CountryAdapter` in `scrapers/adzuna.py`, dedupe on HMAC(source_id), PII isolation, CLI `--source adzuna --country` + `make scrape-adzuna[-nl]`, respx tests. | `make check` passed (127 tests); DE + NL live sweeps complete |
| 4 | 2026-08-22 | Complete | France Travail (FR, Offres d'emploi v2): feasibility gate (robots on 3 hosts + full Licence Offres d'emploi review + live OAuth2/pagination probe), `FranceTravailCollector` with client-credentials auth, TTL reuse and 401 refresh, département-segmented `range` windows, pinned département->NUTS 2024 crosswalk (`scrapers/reference_francetravail.py`), PII isolation, CLI `--source ft` + `make scrape-ft` / `make reference-ft`, respx tests. | `make check` passed (170 tests); DoD sweep complete (17,406 rows) |
| 5 | 2026-08-22 | Gate only | VDAB (BE-Flanders) **feasibility gate + re-scope, no code**: Vacature API v4 found to require an approved partnership + signed samenwerkingsovereenkomst -> recorded **blocked**, not routed around; public vdab.be job-search HTML assessed instead (robots-permitted, disclaimer allows informational re-use) and its **canary passed** (12 pages, 1.2 s, 12/12 HTTP 200, 189 unique ids); roadmap/landscape/feasibility corrected and the Increment 5 kickoff prompt rewritten. | docs only; `make check` unchanged (170 tests) |
| 5 | 2026-08-22 | Complete | VDAB (BE-Flanders) **implementation** on the re-scoped public HTML surface: `VDABCollector` with a per-URL `robots.txt` gate (hard failure, `/api/vindeenjob/` never requested), keyword-sitemap discovery + breadth ordering by postcode, allowlist-only BeautifulSoup/lxml tile parsing, Dutch date parser, HMAC dedupe, pinned postcode->NUTS 2024 crosswalk (`scrapers/reference_vdab.py`, 528 rows), CLI `--source be` + `make scrape-vdab` / `make reference-vdab`, 45 new respx tests. | `make check` passed (215 tests); DoD sweep complete (12,282 rows, 500/500 pages, zero 4xx) |
| 6 | 2026-08-23 | Complete | NAV stillings-feed (NO): feasibility gate (robots absent + full Nynorsk ToS review + live contract re-verification), `NAVFeedCollector` — the lab's first **event-log** source (fold per ad uuid on HMAC source_id), first **source-reported `removed_at`**, and first **native ESCO occupation URI**; token handling with disk cache + 401 rotate-and-replay, `If-Modified-Since` seek / `If-None-Match` revalidation, budgeted ad details, poll cursor, pinned SSB Klass x GISCO fylke/kommune -> NUTS 2024 crosswalk (`scrapers/reference_nav.py`, 370 rows), CLI `--source no` + `make scrape-nav` / `make reference-nav`, 93 new respx tests. | `make check` passed (313 tests); backfill 10,342 rows (20/20 pages) + poll cycle 2,239 rows (6/6, cursor-resumed), zero 4xx, token rotation handled live |
| 7 | 2026-08-23 | **Blocked** (build complete, DoD pending activation) | Työmarkkinatori / Job Market Finland (FI, P67 search API via Kipa): feasibility gate first — **`tyomarkkinatori.fi/robots.txt` disallows `/api/`**, so the source's own KUNTA/MAAKUNTA/ESCO codesets were left untouched and the crosswalk was built from Statistics Finland instead; both Kipa hosts **drop TCP 443 from a non-allowlisted IP** (21 s) so there is **no sandbox** and the contract was pinned from the published OpenAPI. `FinlandTMTCollector` — key auth + optional bearer with 401 refresh-and-replay, streaming NDJSON with drained-then-retried 429/5xx, **client-side watermark** (the API has no cursor and no sentinel), loud schema-drift guard, the lab's **first `skill_mappings`** and second **source-reported `removed_at`**, five-way FINESCO classification (ESCO / ISCO group / national extension / unrecognised / absent); pinned kunta+maakunta -> NUTS 2024 crosswalk (`scrapers/reference_finland.py`, **327 rows, 19/19 NUTS 3, 0 unmatched, 0 ambiguous**); CLI `--source fi` + `--max-rows`/`--status`, `make scrape-finland` / `make reference-finland`, 54 new tests. **KEHA activation notification deliberately NOT submitted** (bound to a Finnish Y-tunnus). | `make check` passed (367 tests); **DoD not met — 0 records**: no key and no IP opening, sweep stops at the robots gate after 94.3 s, no partition written |
| P1 | 2026-08-23 | Complete | **Germany — active lane architecture** (planning, no code): user re-ordered the roadmap to make Germany the active build target; every German surface probed live and the grey-HTML chain **re-ordered by evidence to 10 → 9 → 8** (Stellenanzeigen → Joblift → Kimeta). Key findings: **Kimeta is robots-blocked for this lab** (`*` → `Disallow: /`, verified with `RobotsRule` — DENY on `/jobs/berlin`, `/search`, `/api/job-pdf`); **Joblift is CloudFront-403 at the edge** (robots.txt and its partner-API page both blocked from this egress); **Stellenanzeigen.de is robots-permitted with three advertised sitemaps and `JobPosting` JSON-LD on detail pages** (community scrapers confirm "passive Cloudflare, no active challenge") — it becomes the primary German build; BA portal is robots-allow-all but the Jobsuche data stays agreement-only (access track); BKG Geodatenzentrum robots permits (only GPTBot blocked) and destatis allows with `Crawl-delay: 30`, confirming the German region-crosswalk authority. Germany has **400 NUTS 3 codes** (GISCO 2024, verified). Plan recorded: coverage stack, lanes, mandatory foolproof mechanisms, predetermined backup chain, cross-source overlap stance, and the new `reference_germany.py` prerequisite. | docs only; `make check` unchanged (367 tests) |
| P2 | 2026-08-23 | Complete | **Germany re-assessment under the relaxed constraint** (planning, no code): user **relaxed the ToS/robots gate** for this private educational project. Live probes found the plan's #1 source is now the **BA Jobsuche public website** (~1.9M, SSR plain HTTP, no anti-bot, native ref IDs; its internal REST API is WAF-403 even from a browser); **StepStone** (~1.5M+, SSR, JSON-LD, no Akamai challenge on search) and **Indeed** (~1.5M+, SSR, `data-jk` ids, **litigation history flagged**) are also plain-HTTP accessible; **Kimeta** has no technical anti-bot. **Monster** (DataDome) and **Joblift** (CloudFront 403) and **Interamt** (JS redirect loop) are technically blocked — probe rows. Roadmap tiered German stack rewritten (BA Jobsuche → StepStone → Indeed → Kimeta → Stellenanzeigen → probes → Arbeitnow), feasibility table rewritten from legal to technical verdicts, landscape + risk matrix updated. `reference_germany.py` remains the build prerequisite. | docs only; `make check` unchanged (367 tests) |
| 8 | 2026-08-24 | **Complete** | **BA Jobsuche — Germany #1** (primary build, Germany active lane). Deliverable 1: `scrapers/reference_germany.py` + `data/reference/germany_plz_nuts_2024.csv` (22,140 rows = 4,862 PLZ + 11,000 municipality + 400 Kreis; 400/400 NUTS 3 codes, 0 unmatched; destatis Kreise official AGS→NUTS 2024 key × BKG VZ250_GEM × destatis Anschriftenverzeichnis Zustell-PLZ, validated against Eurostat GISCO; 11 ambiguous PLZ × 397 ambiguous city names; 121 Thuringian stale-VZ250 deviations recorded). Deliverable 2: `scrapers/ba_jobsuche.py` (BAJobsucheCollector — SSR HTML parser, allowlist-only, robots-as-evidence, city→NUTS via crosswalk, 403-rate-limit with 45s cooldown+retry, HMAC dedupe, 25 items/page, 400-page window). `main.py` SourceConfig slug `ba`, `make scrape-ba-jobsuche` / `make reference-germany`. 22 new respx tests (389 total). **DoD verified live:** 400/400 pages, 10,000 rows, `status=complete`, `expected_pages == completed_pages`, `expected_rows == row_count`, zero 4xx, 10,000 unique 64-hex HMAC source_ids, 100% first_published coverage, 358/400 distinct NUTS 3 codes mapped (6,448 mapped, 3,497 unmapped, 55 ambiguous), zero PII. **Honest bound:** 10,000-listing per-query window (400 pages × 25), plus BA rate-limits with 403 after ~50 requests (Apache edge token bucket, ~45s idle recovers); 7 throttle events absorbed in the live sweep. | `make check` passed (389 tests); DoD sweep complete (10,000 rows) |
| P3 | 2026-08-24 | **Complete** | **EU coverage + main-app push-readiness assessment** (planning, no code) — the prep step before the Increment 9 segmented-DE build. Counted rows per EU country across all 11 collection partitions (**379,395 rows, ~322.8k distinct postings** in 7 countries); computed advertised-vs-collected coverage per source (CZ 100% / PL 100% by construction, FR 43.2%, BE 5.3%, NL 2.6%, DE 0.4–0.5% of the ~1.9M stock, NO n/a — event log); verified lab output is byte-compatible with the main app's `stg_postings.sql`/`stg_collection_manifests.sql`; identified `accepted_values: [DE, SE]` (`schema.yml:66`) as the **only** gate blocker — DE is already eligible, the other 6 countries are a main-checkout decision (out of the lab's remit); concluded DE is **pipeline-ready but not coverage-sufficient** (14,841 rows ≈ 0.5% of stock; BA region mapping 64.5%, below the 80% bar) — the Increment 9 plan is the correct readiness step. | docs only; `make check` unchanged (389 tests) |
| 9 | 2026-08-24 | **Cancelled 2026-08-31** — census completion cut (see P4); 203,674 rows / 65 partitions stand untouched | **BA Jobsuche — segment-provenance German regional coverage** (Increment 9, Germany step 2; plan `.kilo/plans/1787577245495-ba-segment-provenance-de-coverage.md`). **Gate probes (live, ~40 paced requests, zero 4xx):** Bundesland/city/PLZ all resolve as `wo=`; **`wo=Landkreis+…` is broken** (every variant returns the same 7 Rosenheim postings — a fuzzy-match miss) and compound `-Kreis` names are unreliable (`Rhein-Sieg-Kreis` → Rüdesheim), so the level-2 backbone uses **municipality/PLZ segments** (10,761 from the crosswalk: 10,085 unique-name municipalities + PLZ for the 397 ambiguous names, each PLZ a single NUTS 3); `umkreis=0` confirmed tight ⇒ **Tier 3 = `mapped`**; no server-rendered total ⇒ page-400 oracle; `veroeffentlichtseit` filter works (level-4 axis); Berlin/München/Hamburg truncate at 400 pages. **Built:** `scrapers/ba_segments.py` (Segment/SegmentFrontier, `build_initial_frontier`, Bundesländer with city-state pre-subdivision), `normalize_location()` in `scrapers/ba_jobsuche.py` (Tier-1 qualifier strip + NUTS-1 alias map, Tier-2 segment-context disambiguation, Tier-3 single-NUTS-3 provenance gated on `umkreis=0`, non-geographic markers → `ambiguous`), segmented `BAJobsucheCollector` mode (completeness oracle, breadth-first region ordering, atomic segments, resumable frontier saved after every segment), scope `de-stock-segmented`, `main.py` `--segmented/--max-segments/--min-level/--umkreis`, per-chunk timestamped partitions, `make scrape-ba-segmented` + `make check-ba-segmented` (push-readiness gate: ≥85% mapped, ≥390/400 NUTS 3, ≤5% unmapped). 21 new respx tests (410 total). **Live census progress (63 chunks, ~6 h of paced collection):** 65 reconciled partitions, **203,674 rows**, **mapped 203,215 (99.77%), ambiguous 459 (all non-geographic markers), unmapped 0, low_confidence 0**; Tier breakdown 186,761 / 2,284 / 14,170 (Tier 1/2/3); **PII scan clean** (0 e-mails/URLs/native refs/PLZ/city strings); **zero 4xx**, throttles absorbed as `throttle_events`; München subdivided at the 400-page cap (PLZ children enqueued), **zero truncated segments left unsubdivided**; every partition `status=complete` and reconciled. **Remaining:** ~8,171 frontier segments (~20 h at the current pace) until `make check-ba-segmented` passes (124/400 NUTS 3 at session end). | `make check` passed (410 tests); census resumable at `data/state/ba_segment_frontier.json` |
| P4 | 2026-08-31 | **Complete** | **Descoping decision — German census cancelled; BA Jobsuche re-planned as a frozen NUTS-3 panel** (planning, no code): census completion (~8,171 pending frontier segments, ~20+ h) cancelled **not paused** — a long gap followed by resumption of the same scope would record a mass fake `inferred_absence` closure spike downstream (closures are inferred from any later sweep of the same scope). New plan (roadmap step 2b): envelope probe FIRST (does the BA response envelope carry a total-hits field? if yes, one request per region = exact regional counts, whole map = 400 requests; outcome to be recorded in `SCRAPER_FEASIBILITY.md`), 400-unit NUTS-3 frame replacing the ~10.8k municipality/PLZ frame (destatis Kreise = authoritative AGS→NUTS 2024 key, all 400 GISCO codes; VZ250 names-only), frozen panel (byte-identical query set, seed recorded), cap-as-scope honesty (page cap in `scope_json` + `coverage_limitations`), burst = 400-query region probe + ~5 daily sweeps (~30 min each, ~3 h over a week). Cuts recorded in roadmap + landscape: StepStone + Kimeta (non-additive second DE source — cross-source counts never summed downstream), Indeed (stays charter never-build), other-country re-sweeps (conditional on the observatory's live-service budget only). Acceptance criteria + weekly-cadence design recorded in charter/roadmap/feasibility. | docs only; `make check` re-run and green (410 tests) |
| 2b | 2026-09-02 | **Complete** | **BA Jobsuche frozen NUTS-3 panel** (Germany step 2b; scope `de-nuts3-panel`, replaces the cancelled census). **Probes (live, 1 s pacing):** the response envelope **does** carry a total-hits field — `suchergebnis.maxErgebnisse` inside the SSR state `<script id="ng-state">` (Berlin 30,334 / Hamburg 24,474 / Rosenheim 3,128), plus `woOutput.bereinigterOrt` + `suchmodus` as a per-query locality echo; **BA has no Kreis-level addressing** (`wo=Landkreis X` returns the identical 7 Rosenheim postings for every Kreis, `suchmodus` ∈ {`ORTSUCHE`, `UMKREISSUCHE`, `UNGUELTIG`}), Kreis names as places fail 10/16, anchor postcodes with `umkreis=0` hit 18/20 with perfect locality, and the crosswalk's `plz` slice turns out to be **administration postcodes only** (Hof's 95028/95030 are `unmapped`), so region attribution must come from the query context, not tile postcodes. **Built:** `scrapers/ba_panel.py` (pinned panel, candidate generation, membership hash, scope params, per-region side file), `parse_search_envelope()` + `_fetch_panel()` in `scrapers/ba_jobsuche.py` (declared page cap, plan from the advertised total, locality assertion, HMAC dedupe, 403 cooldown absorbed as throttle events), `main.py --panel`, `make scrape-ba-panel`, `make check-ba-panel` (`scripts/check_ba_panel_readiness.py`, one line per assertion), probe scripts `probe_ba_envelope.py` / `probe_ba_region.py` / `probe_ba_resolve.py` / `pin_ba_panel.py`, 29 new tests (439 total). **First sweep attempt REJECTED on breadth (370/400) and its partition deleted** — the reference-only anchor rule is degenerate in rural regions (every municipality has one postcode ⇒ alphabetically first village, 22 zero-stock anchors, 33 fuzzy misses); replaced by a **pinned artifact** `data/reference/ba_panel_nuts3.json` (175 live requests + 268 measurements reused; 399/400 regions non-empty). **Sweep 1 accepted (`20260902T080422Z`): 400 regions, 1,315/1,315 pages, `status=complete`, `expected_rows == row_count == NDJSON lines = 28,900`, 393/400 NUTS-3 regions mapped, one membership hash `545b162ec6e5fbdc…`, zero failed requests (25 absorbed throttles), PII clean, 270 regions at the declared cap, advertised totals summing to 372,413.** Next: sweeps 2–5 on subsequent days (~40 min each, `make scrape-ba-panel *> logs/ba-panel-sweepN.log`, read only the tail); after sweep 5 `make check-ba-panel` must still show one membership hash. Weekly cadence by design. | `make check` green (439 tests); `make check-ba-panel` 6/6 assertions pass |
## Session Notes

### 2026-08-20 - Increment L0 (context cleanup)

- Removed `SOURCE_FEASIBILITY.md` (main project's anti-German-collection
  decision record) and replaced it with `SCRAPER_FEASIBILITY.md`, a per-target
  checklist with no inherited rejections.
- Added `SCRAPERS.md`, the governing charter: network allowed by design,
  robots.txt + Crawl-Delay + ToS review before building, 1s+ pacing, PII-free
  extraction, HMAC pseudonymization, and the SAFE_FIELDS + manifest output
  contract.
- Rewrote the worktree-local `AGENTS.md` so it points at `SCRAPERS.md` and
  `SCRAPER_FEASIBILITY.md`.
- Replaced the main-project `SESSIONS.md` history with this lab log.
- Replaced the main `Makefile` (offline gate) and `pyproject.toml` (dlt/dbt)
  with lab-owned versions; scraper deps added (httpx, beautifulsoup4, lxml).
  `uv sync` regenerated the lockfile.

### 2026-08-21 - Increment 1 (CBOP / ePraca Poland)

- **Feasibility gate** recorded in `SCRAPER_FEASIBILITY.md`: robots.txt absent
  (404, nothing disallowed), ToS allowed (CC BY 3.0 PL + official "Dla
  integratorów" section), public search JSON API at
  `POST /portal-api/v3/oferta/wyszukiwanie` with body `{"kodJezyka":"PL"}`
  (no auth, Spring Data pagination). The SOAP integrator service was verified
  live to require a ministry-registered Partner ("Niepoprawna autoryzacja") and
  is therefore not used.
- **Collector Interface** built: `scrapers/base.py` (`BaseCollector` ABC,
  `RawRecord`/`NormalizedRecord` on the SAFE_FIELDS allowlist, `SweepWriter`
  with manifest reconciliation), `scrapers/robots.py` (`RobotsRule` +
  `PacingGate` 1s floor), `scrapers/retry.py` (`with_backoff` honoring
  Retry-After), `scrapers/sanitize.py` (HMAC-SHA256 pseudonymization + `.env`
  fallback), `scrapers/validate.py` (SAFE_FIELDS enforcement, Arrow schema,
  optional Parquet export).
- **PolandCollector** (`scrapers/poland_cbop.py`, alias `CBOPCollector`) walks
  the portal-api v3 search pages; PII fields (email, phone, contact person,
  employer, addresses) excluded by `NormalizedRecord(extra="forbid")`.
- **CLI** `main.py --source pl --date YYYY-MM-DD [--max-pages N] [--parquet]`
  and the `make scrape` target.
- **Tests:** 69 passing (retry, robots, sanitize, validate, respx-mocked
  collector, sweep writer; the existing JobTech output-contract tests in
  `tests/test_probe.py` pass unchanged). `make check` green.
- **Live canary:** 1 page, 100 rows, zero 4xx; recorded in the feasibility doc.
- **Full DoD sweep:** 22,068 observations, 221/221 pages, `status=complete`,
  `expected_rows == row_count == 22,068`, zero 4xx, all source_ids unique
  64-hex HMAC digests, no PII present in output. Partition at
  `data/raw/collections/cbop/pl-all-active/20260821T000000Z/`.
- **Notes for later increments:** CBOP exposes no per-offer total vacancy count
  in the list payload (`number_of_vacancies` defaults to 1); NUTS and ESCO
  mapping are deferred (a TERYT `miejscowoscId` -> NUTS crosswalk would fit
  Increment 2's Czech region-mapping work).

### 2026-08-22 - Increment 2 (Úřad práce / MPSV Czechia) — PLANNING

- **Housekeeping:** resolved a pre-existing in-progress merge of
  `EU-Tech-Labor-Observatory/main` into `scrapers` that had left conflict
  markers in the lab `Makefile` and `SESSIONS.md` (both blocked `make check`).
  Both files were resolved to the lab/HEAD versions (lab gate
  `check: lint types test`, lab session log); main's cleanly-merged files
  (`.gitignore`, `scripts/collect.py`, `tests/test_probe.py`) were kept. Merged
  as one `chore(dev)` commit `eb9cbc5`. `make check` now green at **83 tests**
  (main's merged `test_probe.py` adds 14 JobTech output-contract tests).
- **Feasibility gate recorded in `SCRAPER_FEASIBILITY.md` (live, network
  allowed):** `data.mpsv.cz/robots.txt` allow-all (no Crawl-Delay);
  `data.gov.cz/robots.txt` disallows `/sparql*`/`/fct/`/`/describe/`/`/zdroj/`
  (rules out the NKOD SPARQL path, irrelevant to the dump host). ToS allowed:
  MPSV "Podmínky užití" uses the standard NKOD open-data declarations (no
  copyrighted works, no database right, no personal data) + CC BY 4.0 on
  data.gov.cz; legal basis zákon č. 435/2004 Sb. No documented rate limits.
  **Decision: implement.**
- **Live probe of "Volná místa za celou ČR":** full active-set dump
  `GET https://data.mpsv.cz/od/soubory/volna-mista/volna-mista.json` — single
  JSON object `{"polozky": [...]}`, **no pagination**, ~186 MB, **38,903
  records** at 2026-08-21 (DoD floor ≥5,000 exceeded ~7.8×). HTTP 200 with
  `ETag`/`Last-Modified`/`Accept-Ranges` (conditional GET possible), zero 4xx,
  no auth/anti-bot. Daily refresh (source "1x denně"; probe `Last-Modified`
  2026-08-20 20:06 UTC).
- **Field mapping candidates (100% present):** `portalId` (native id → HMAC),
  `datumVlozeni` (first_published), `datumZmeny` (last_modified), `pocetMist`
  (number_of_vacancies), `mistoVykonuPrace.pracoviste[].adresa.kraj.id`
  (region, **90.7% coverage**). `expirace` only 7.4% (publication expiry).
- **NUTS crosswalk is trivial:** the published `kraje` codelist carries
  `kodNuts3` (CZ010–CZ080, unchanged in NUTS 2024) plus fallback codelists
  `okresy` (78, has `kraj`) and `obce` (6,258, has `okres`). Pin them as
  `data/reference/mpsv_*.csv` following `geography_nuts_2024.csv`; collector
  never calls live codelists.
- **PII confirmed present** (contact names, emails, telephones, street
  addresses/PSC in `prvniKontaktSeZamestnavatelem`, `pracoviste[]`,
  `zamestnavatel`): allowlist-only parse + `extra="forbid"` backstop, plus a
  PII-isolation test in the plan.
- **Delta design for the DoD:** the dump is the active set; closures are derived
  by a reconciliation step that compares **HMAC source_ids only** across
  consecutive partitions and writes `closures.ndjson` with `removed_at`
  (`expirace` when source-reported, else next-sweep `observed_at`). No native
  ids or PII in the comparison or output.
- **Plan written to `.kilo/plans/1787351616165-mpsv-cz-plan.md`** (endpoint +
  request contract, crosswalk strategy with mapped/ambiguous/low_confidence/
  unmapped statuses, SAFE_FIELDS mapping table, delta semantics, respx test
  plan, risks + go/no-go). Go/no-go: **GO** — no blockers.

### 2026-08-22 - Increment 2 (Úřad práce / MPSV Czechia) — IMPLEMENTATION

- **Crosswalk reference built and committed** (`make reference-mpsv` via
  `scrapers/reference_mpsv.py`, opt-in network): `mpsv_kraje_nuts_2024.csv`
  (14 rows, `kodNuts3` CZ010–CZ080), `mpsv_okresy_kraj_2024.csv` (78),
  `mpsv_obce_kraj_2024.csv` (6,258), plus `reference_manifest_mpsv.json`
  provenance. Follows the `geography_nuts_2024.csv` column pattern; the
  collector reads only the pinned CSVs, never live codelists.
- **`MPSVCollector`** (`scrapers/czech_mpsv.py`): single streamed GET of the
  full dump to a temp file (`MPSV_DUMP_URL`), no pagination
  (`total_pages == completed_pages == 1`); pydantic `extra="ignore"` models
  with required `portalId`/`datumVlozeni`/`datumZmeny`/`pocetMist` (schema
  drift fails loudly); region chain workplace kraj (mapped) → contact address
  (low_confidence) → okres (mapped/ambiguous) → obec (mapped) → unmapped;
  `occupation_mapping_status=not_present` (deferred); accumulates
  `expirace_by_source_id` for the delta step.
- **Delta reconciliation** (`scrapers/reconcile_mpsv.py`, `make reconcile`):
  compares **HMAC source_ids only** across the two most recent partitions;
  writes `closures.ndjson` (source_id, removed_at, source, scope_id, sweep_id
  — strict SAFE_FIELDS subset) with `removed_at` = source-reported `expirace`
  when the older partition carried one inside the window, else the newer
  sweep's `observed_at`; `integrity_ok` asserts newer == unchanged+added and
  older == unchanged+closed.
- **CLI + Makefile:** `main.py --source cz|mpsv` (source registry + typed
  `SourceConfig`; `--max-pages > 1` rejected for the single-dump source) and
  `make scrape-cz`; `BaseCollector` gained `total_elements`/`total_pages`/
  `completed_pages` counters (additive, JobTech output-contract tests
  unchanged).
- **Tests:** 30 new (collector/respx, crosswalk statuses, reconciliation
  delta/expirace/integrity, PII isolation). `make check` green at **113 tests**
  (ruff + mypy strict clean).
- **Full DoD sweep (live):** two consecutive daily sweeps (2026-08-22 and
  2026-08-23) each wrote **38,903 observations, 1/1 pages, `status=complete`,
  `expected_rows == row_count == 38,903`**, zero 4xx; `region_mapping_status`
  populated on 100% of rows with **98.8% region-mapped** (mapped 35,975 /
  low_confidence 2,152 / ambiguous 292 / unmapped 484); all source_ids unique
  64-hex HMAC digests; zero PII tokens in the raw NDJSON blob; `meta.ndjson`
  carries 2,864 expirace records. Reconciliation between the two runs:
  `added 0, closed 0, unchanged 38,903, integrity OK` (the dump was unchanged
  between runs minutes apart; the added/closed/removed_at logic is pinned by
  the fixture tests). Partitions at
  `data/raw/collections/mpsv/cz-all-active/2026082{2,3}T000000Z/`.
- **Roadmap/feasibility updated:** Increment 2 marked **DONE 2026-08-22**;
  feasibility row records the live sweep evidence.

### 2026-08-22 - Increment 3 (Adzuna — multi-country adapter) — IMPLEMENTATION

- **Feasibility gate recorded in `SCRAPER_FEASIBILITY.md` (live):** `api.adzuna.com/robots.txt`
  → `User-agent: * / Disallow: /` (blanket disallow on the API host, standard
  keyed-API pattern; unauthenticated requests fail nginx 400); `adzuna.com` /
  `www.adzuna.com` robots.txt → 405 (no robots handler on consumer hosts, never
  touched). ToS (developer.adzuna.com/docs/terms_of_service): **allowed with
  conditions** — "Permissible Use: 1. Publishing ad listings, 2. Jobsworth
  salary estimates, 3. **Personal research**"; academic/org use permitted for a
  14-day validation period, ongoing research needs written consent/licence;
  mandatory attribution ("The Adzuna API" + link) wherever data is published.
  Documented free-tier limits: **25 hits/min, 250 hits/day, 1000/week,
  2500/month**; 429 + Retry-After honored. **Decision: implement.**
- **Credentials:** `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` were absent from `.env`;
  per the charter/task they were requested from the user (never hardcoded or
  invented) before any live call. User added them to `.env`; verified present
  (no values printed/logged).
- **Live contract probe (STEP 4), DE + NL, 2.5 s pacing, ~30 hits:** envelope
  `{__CLASS__, count, mean, results}`; `count` = DE 1,155,948 / NL 190,606
  active listings; 50 results/page, pages 1..24 all 200, zero 4xx, zero 429.
  Result fields: `id`, `adref` (JWT-style token embedding the same `id` —
  verified base64 `"i":"NTgz..."`), `created` (ISO 8601 UTC), `category
  {label,tag}`, `company {display_name}`, `location {area[], display_name}`,
  `title`, `description`, `redirect_url`, `salary_*`, `latitude/longitude`.
  **`id` type differs by country: string on DE, integer on NL** (model coerces
  via field validator). **Per-query result window discovered live:** pages
  beyond ~100 return listings already seen on earlier pages (`fresh_ids=0` at
  pages 120–200) — one all-active query yields at most ~5,000 unique rows; the
  `count` field advertises the total stock, not the query window.
- **Honest cap finding (recorded plainly, no padding):** the free tier's
  250 hits/day plus Adzuna's ~100-page per-query window make the roadmap's
  "≥100,000 rows in one DE sweep" physically impossible (~23k segmented hits
  for the 1.16M DE stock). Stated in the feasibility row and each manifest's
  `coverage_limitations`; the collector pages correctly to any budget
  (validated in mocked tests incl. >100k rows).
- **`AdzunaCollector` + `CountryAdapter` (`scrapers/adzuna.py`):** one class,
  all 18 country domains; `CountryAdapter` (country_code, expected_country,
  locale, language, source_version, scope_id, scope_params, licence_reference,
  access_method, freshness, coverage_limitations) shipped for DE + NL in an
  `ADZUNA_ADAPTERS` registry. Pagination `.../search/{page}` with
  `results_per_page=50`; pacing ≥2.5 s honoring the documented 25/min; retries
  via `scrapers/retry.py` (429 + Retry-After); dedupe on HMAC source_id across
  pages and optional segments/categories; `region_mapping_status=not_present`
  (location free text only, NUTS crosswalk deferred); `occupation_mapping_status=
  not_present` (category→ESCO deferred); `number_of_vacancies=1`;
  `first_published` from `created`; `last_modified`/`removed_at` absent
  (absence-based closure stamping deferred, MPSV reconcile stays MPSV-specific).
  Source_id policy: HMAC of native `id` (stable ad ref; `adref` embeds the same
  id — cross-board merge impossible from the search payload, recorded as a
  coverage limitation).
- **PII:** `title`, `description`, `company`, `redirect_url`, contacts and all
  free text excluded by the allowlist-only parse + `NormalizedRecord(extra=
  "forbid")`; PII-isolation test asserts none of the raw payload's private
  tokens appear in output.
- **CLI + Makefile:** `main.py --source adzuna --country de|nl` (source
  registry + typed SourceConfig extended; credentials loaded via
  `adzuna_credentials()` which raises before any network call when absent);
  `make scrape-adzuna` / `make scrape-adzuna-nl`.
- **Tests:** 14 new (pagination + normalization, PII isolation, 429 retry with
  Retry-After, NL config-only differences, segment dedupe, category segments,
  page budget, empty-page stop, missing/integer id, datetime, credentials
  loading + missing-guard, native-id never in output). JobTech output-contract
  tests pass unchanged. `make check` green at **127 tests** (ruff + mypy strict
  clean).
- **Live DoD sweeps:** DE `de-all-active` 20260822T000000Z — **100/100 pages,
  4,841 rows, `status=complete`, `expected_rows == row_count`, zero 4xx**;
  NL `nl-all-active` 20260823T000000Z — **100/100 pages, 4,956 rows,
  `status=complete`, `expected_rows == row_count`, zero 4xx** (same class,
  config-only change; NL ran under the next-day daily quota). Advertised counts
  (DE 1,155,948 / NL 190,606) recorded in the manifests' `coverage_limitations`;
  all source_ids unique 64-hex HMAC digests; zero PII tokens in the raw NDJSON
  blobs; native ids never present. Partitions at
  `data/raw/collections/adzuna/{de-all-active,nl-all-active}/`.
- **Roadmap/feasibility updated:** Increment 3 marked **DONE 2026-08-22**;
  feasibility row records robots/ToS verdict, the true free-tier + per-query
  caps, and the live sweep evidence. The written manifests carry the
  pre-refinement coverage text (240-page constant); the adapter ships the
  corrected text (100-page budget) for future sweeps.

### 2026-08-22 - Increment 4 (France Travail FR: API Offres d'emploi v2)

- **Feasibility gate (STEP 3), all live.** robots.txt on every host the work
  touches: `api.francetravail.io` → `User-Agent: * / Disallow: /` (blanket
  disallow on the keyed API host, the same pattern as `api.adzuna.com` in
  Increment 3 — it governs *unauthenticated* crawling, and every unauthenticated
  request answers 401; OAuth2 access under the accepted licence is the API's only
  and documented access mode); `francetravail.io` (portal) allows everything
  except `*utm_campaign*`, `/api-peio/`, `*api-peio*`, `*oauth2*` (none were
  requested); `entreprise.francetravail.fr` (token host) 308-redirects its robots
  to `pro.francetravail.fr/robots.txt` → `Disallow:` (allow all). Legacy
  `api.pole-emploi.io` refuses connections; legacy `entreprise.pole-emploi.fr`
  token host still answers identically.
- **Licence review (14 articles).** The **Licence de réutilisation de la base de
  données des offres d'emploi de France Travail** cedes free, non-exclusive
  extraction and reuse rights (Art. 1.1). Conditions recorded and satisfied:
  Art. 4 attribution (source + last-update date + licence link → manifest
  `licence_reference`), Art. 5.2 call the API ≥ once/24 h and preserve
  publication/update dates, **Art. 7 anonymization of a derived database — drop
  employer name/description/URL, contact name and coordinates, phone numbers,
  offer URLs and the postcode, INSEE code and commune label of the workplace**
  (exactly what SAFE_FIELDS already excludes; the location identifiers are used
  transiently to derive NUTS 3 and never persisted), Art. 8 GDPR
  purpose-compatibility + EU storage, Art. 3 no sub-licensing, Art. 10 licence
  lapses after 12 months of inactivity, Art. 13 audit right. **Roadmap
  correction:** the API is in the "API en accès libre" tier — a self-service
  account plus click-through licence acceptance, not a counter-signed contract.
- **Credentials / auth state.** `FRANCE_TRAVAIL_CLIENT_ID` /
  `FRANCE_TRAVAIL_CLIENT_SECRET` were present in `.env` and correctly shaped
  (`PAR_<21-char slug>_<64 hex>` / 64 hex) but the token endpoint answered
  `400 {"error":"invalid_client"}` for **every** documented variant (body creds,
  Basic auth, with/without scope, `application_<id>` scope prefix, legacy host,
  swapped id/secret); `realm=/individu` answered `Invalid realm`, proving the
  request parsed and the credential pair itself was rejected. Reported to the
  user instead of guessing or inventing keys (charter Rule 5 / task STEP 3): the
  account existed but **the Licence Offres d'emploi had not been accepted**.
  After acceptance the identical request returned `200 {token_type: Bearer,
  expires_in: 1499, scope: "api_offresdemploiv2 o2dsoffre"}`. No credential
  value was printed or logged at any point.
- **Live contract probe (STEP 4).** `GET /partenaire/offresdemploi/v2/offres/
  search?range=a-b` answers **`206 Partial Content`** with
  `Content-Range: offres a-b/503356` and `accept-range: 150`. Hard caps probed:
  window > 150 items → `400 "La plage de résultats demandée est trop
  importante."`; start > 3000 → `400 "La position de début doit être inférieure
  ou égale à 3000."` ⇒ **3,150 offers per query** against a **~503–504k**
  national active stock. Deep windows return fresh ids (no Adzuna-style
  recycling: windows 0/150/1000/1150/2000/3000 each yielded `fresh=150`).
  Rate limits: documented 10 appels/seconde, confirmed by
  `x-ratelimit-replenish-rate-clientidlimiter: 10` headers. Invalid/expired
  token → **401 with empty body** + `WWW-Authenticate: Bearer`. Field shapes
  (300-offer sample): `id` (7 chars), `dateCreation` / `dateActualisation` /
  `nombrePostes` / `romeCode` **100%**, `lieuTravail.commune` 95.0%,
  `codePostal` 95.3%, `libelle` 100% (`"<dép> - <commune>"`). Référentiels:
  `departements` 101, `metiers` 1,911, `regions` 18, `communes` 35,015.
- **Region mapping decision (the increment's real hurdle).** France exposes no
  NUTS codes, so `scrapers/reference_francetravail.py` builds a pinned crosswalk
  from FT `referentiel/departements` × Eurostat GISCO **NUTS 2024**
  (`NUTS_AT_2024.csv`, FR level 3 = 101 codes) joined on the département name
  (accent/case/punctuation-insensitive): **101/101 matched, zero leftovers, zero
  manual overrides** →
  `data/reference/francetravail_departements_nuts_2024.csv` (+ hashed
  reference manifest, `make reference-ft`). Resolution chain at normalize time:
  `commune` INSEE → `mapped`, `codePostal` → `low_confidence` (Corsican `20xxx`
  cannot separate 2A/2B → `ambiguous`), `libelle` prefix → `low_confidence`,
  otherwise `unmapped`. **Occupation:** `romeCode` is present on every offer but
  no pinned ROME → ESCO 1.2.1 crosswalk exists, so the status is `unmapped` with
  method `deferred_rome_to_esco` — deliberately *not* `not_present` as in
  Increments 1–3, where the source exposed no occupation code at all.
- **`FranceTravailCollector` (`scrapers/france_travail.py`).** OAuth2
  client-credentials with lazy minting, TTL reuse (`expires_in` minus a 60 s
  skew) and a single refresh-and-replay on 401; `range`-window pagination inside
  the 150-item / 3000-start caps; segmentation over the 101 départements plus one
  unsegmented query that records the national advertised total; dedupe on HMAC
  `source_id` across segments; pacing at the charter's 1 s floor (10× inside the
  documented 10 req/s) with `Retry-After`/429 backoff from `scrapers/retry.py`;
  `first_published`=`dateCreation`, `last_modified`=`dateActualisation`,
  `number_of_vacancies`=`nombrePostes`, `removed_at` absent (absence-based
  closures across sweeps). Reused `base.py`, `robots.py`, `retry.py`,
  `sanitize.py`, `validate.py` unchanged.
- **PII.** `description`, `intitule`, `entreprise`, `contact`, `origineOffre`,
  `agence`, `salaire` and the `lieuTravail` identifiers are simply not declared
  on the payload models (`extra="ignore"`), with `NormalizedRecord(extra=
  "forbid")` as the backstop; the PII-isolation test asserts none of the raw
  private tokens — including postcode and INSEE code, per licence Art. 7 —
  appear in a dumped record.
- **CLI + Makefile.** `main.py --source ft|fr|francetravail` (typed
  `SourceConfig` entry, scope `fr-all-active`, credentials via
  `france_travail_credentials()` which raises before any network call);
  `make scrape-ft` and `make reference-ft`.
- **Tests.** 43 new respx tests: documented token-request body, token minted once
  and reused, TTL expiry re-mint (injected clock), 401 refresh-and-replay,
  persistent 401, token without `access_token`, `range` window pagination, the
  3000-start cap (21 windows = 3,150 offers), short/empty/204 windows, page
  budget, segment dedupe, default segments covering every département, 429 with
  `Retry-After`, 500 propagation, PII isolation, unique source_ids, missing id,
  `nombrePostes` edge cases, ROME present/absent statuses, date and
  `Content-Range` parsing, the full region-resolution chain (commune/postcode/
  libellé/Corsica/foreign/region-only), crosswalk loader errors and hashes,
  short HMAC key, missing credentials. JobTech output-contract tests pass
  unchanged. `make check` green at **170 tests** (ruff + mypy strict clean).
- **Live DoD sweeps.** `fr-all-active` **20260822T000000Z** — **120/120 windows,
  17,406 rows** (594 cross-segment duplicates dropped), `status=complete`,
  `expected_rows == row_count == NDJSON lines`, **zero 4xx/401**; region
  **mapped 98.1%** (17,081), low_confidence 294, unmapped 31, **100 distinct
  NUTS 3 codes**; dates on 100% of rows; unique 64-hex HMAC source_ids; PII scan
  found 0 e-mails, 0 URLs, 0 postcodes, 0 INSEE codes, 0 native ids (the only
  string fields are the allowlist's enums/timestamps/NUTS codes). Second
  consecutive daily sweep **20260823T000000Z** — **1500/1500 windows, 217,455
  rows**, `status=complete`, reconciled, zero 4xx/401, region mapped 98.1%,
  177.8 MB; **token TTL honored live: 2 token requests for 1,500 API calls**,
  the second minted 1,439 s after the first (TTL-driven, not 401-driven).
  Cross-sweep continuity: 17,181/17,406 (98.7%) source_ids reappear, 225 absent
  (closure candidates; budgets differed, so indicative only).
- **Honest cap statement.** ≥10,000 offers per sweep is easy, but a *complete*
  national snapshot is impossible in one pass: 3,150 offers/query × 101
  départements ⇒ ≤ ~318k of the ~503k active stock, and offers whose
  `lieuTravail` carries no département (region-only or foreign, ~2% of the
  sample) are reachable only through the unsegmented query and stay
  region-unmapped. Recorded in the feasibility row and in every manifest's
  `coverage_limitations`.
- **Roadmap/feasibility updated:** Increment 4 marked **DONE 2026-08-22**; the
  feasibility row carries the robots reading, the full licence analysis, the
  probed caps, the auth/licence timeline and the sweep evidence.

### 2026-08-22 - Increment 5 gate (VDAB BE-Flanders: API blocked, public site re-scoped)

Gate-only session: no collector was written. The roadmap's premise for
Increment 5 turned out to be wrong, so the increment was re-scoped before any
code existed.

- **Surface A — Vacature API v4: BLOCKED.** The roadmap and landscape both
  described "free API key via app registration (`X-IBM-Client-Id`)". VDAB's own
  documentation says otherwise: *"Je mag de Vacature API gebruiken, **nadat VDAB
  een partnership met jou heeft goedgekeurd en na het ondertekenen van een
  samenwerkingsovereenkomst**. Je mag de Vacature API enkel voor professionele
  doeleinden gebruiken. De data-uitwisseling via de API moet een toegevoegde
  waarde hebben voor VDAB en voor je organisatie."*
  (`extranet.vdab.be/api-center-excellence-coe/vacatures-ophalen-met-de-vacatures-api`),
  and the access PDF confirms *"stelt VDAB, waar nodig, een contract op. Nadat je
  dit contract hebt ondertekend, kan je het gewenste API-product aanvragen"*.
  The portal's own `tsandcs` page is a stub. Recorded as **blocked** and **not
  routed around** (charter feasibility gate); re-openable only as an
  access-request task, like BA Jobsuche's HR-BA-XML route.
- **Surface B — public job-search site: PERMITTED, and it is the new scope.**
  `www.vdab.be/robots.txt` (3,564 bytes, no `Crawl-Delay` for `*`) **advertises
  six sitemaps** and allows `/vindeenjob/jobs/<slug>`, `/vindeenjob/vacatures`
  and `/vindeenjob/vacatures/<id>/<slug>`. The vdab.be disclaimer grants re-use
  in as many words: *"Je mag informatie op onze website kopiëren, afdrukken en
  gebruiken voor informatieve doeleinden"*, with the VDAB name/logo protected as
  trademarks (never reproduced in output). Employer terms note that published
  vacancies "can also get a place on other jobsites and in Google results", so
  onward publication is contemplated.
- **The important robots finding.** `/api/vindeenjob/` — the Angular app's own
  JSON API — is **`Disallow`ed**, along with `/vacatures/`, `/include/vacature/`,
  `/zoeken/` and `/vindeenjob/prive/`. That is precisely the path the public
  third-party scrapers use ("intercepts VDAB's Angular API responses"), so the
  easy route is **off-limits here** even though it works; an undocumented
  `/rest/vindeenjob/v2/vacatures/zoek` also answered **403** live. The collector
  will read only the server-rendered landing pages and the advertised sitemaps.
- **Data surface probed.** `/vindeenjob/jobs/<postcode>-<gemeente>` renders **28
  vacancy tiles** server-side (title, employer, contract type, `Online sinds`
  date, `/vindeenjob/vacatures/<id>/<slug>` link) and advertises its own segment
  total (`<strong>1627</strong><span>jobs gevonden`). **No in-page pagination
  exists:** `?limit=100`, `?page=2` and `?start=15` all return the byte-identical
  28-tile page and `/2` 404s. The SPA routes (`/vindeenjob/vacatures`, every
  detail URL) return the same 46,339-byte Angular shell with **0** `ld+json`
  blocks — there is no server-rendered detail page to parse. Sitemaps give the
  second axis: `sitemap/vindeenjob/vacatures/index.xml` → 214 weekly child
  sitemaps (295–1,898 vacancy URLs each, **with `<lastmod>`**),
  `vindeenjob/jobs/nc/sitemap/*` → **34,903** landing pages, plus 513 gemeente
  and 451 employer pages. Search page advertises **232,944** active jobs.
- **Canary test PASSED** (mandatory for HTML sources): 12 postcode landing pages,
  serial, **1.2 s pacing**, 189 records (≤100-record rule respected per page):
  **12/12 HTTP 200, zero 4xx, zero blocks, no Cloudflare/Akamai headers** (server
  is `envoy`); 189 unique ids from 255 tiles — overlap is real (`1000-brussel`,
  `-stad`, `-gombe-kinshasa` share one result set), so HMAC dedupe is mandatory;
  `Online sinds` date and contract label on **100%** of tiles. **Deliberate
  deviation from the roadmap's canary recipe:** user-agents were **not**
  randomized — obscuring identity contradicts the charter's ethical stance, and a
  single honest contactable UA drew zero blocks.
- **Region mapping decision (better than expected).** Basisregisters Vlaanderen —
  the Flemish government's authoritative address register, open JSON-LD, no
  robots file — returns NUTS 3 **directly**: `api.basisregisters.vlaanderen.be/v2/postinfo/9000`
  → `{"gemeente": {...\"Gent\"}, "nuts3": "BE234"}`. `nuts3` is on the detail
  payload only (not the 500-per-page list), so a pinned builder walks the Flemish
  postcodes once (`make reference-vdab`, same shape as Increments 2 and 4).
  Eurostat GISCO `NUTS_AT_2024.csv` supplies the validation set: Belgium has 44
  NUTS 3 codes, **22 Flemish** (`BE21x`–`BE25x`). Occupation stays
  `not_present`: the public tiles carry no ROME/C2/ISCO code.
- **Honest coverage statement.** ≥5,000 rows is comfortable (28 tiles ×
  ~180–400 landing pages at 1 s ≈ 3–7 min), but the full 232,944-vacancy stock is
  **not** reachable this way without walking a large share of the 34,903 landing
  pages; that gap must be stated in `coverage_limitations` on every manifest.
- **Docs updated:** `SCRAPER_FEASIBILITY.md` gains an Increment 5 entry with
  **both surfaces** recorded (A blocked, B implement); `SCRAPER_ROADMAP.md`
  Increment 5 re-scoped to HTML with the canary result, VDAB's API added to
  "Not planned", the risk-matrix row and the canary-serialization note adjusted;
  `SCRAPER_SOURCE_LANDSCAPE.md` VDAB entry split into the two surfaces and its
  volume tier corrected M → L (~233k); `.kilo/plans/increment-5-vdab-prompt.md`
  rewritten for the public-site scope.

### 2026-08-22 - Increment 5 build (VDAB BE-Flanders public site)

Implementation session for the re-scoped Surface B. The blocked Vacature API was
not touched and not worked around, and the robots-disallowed `/api/vindeenjob/`
was never requested — that prohibition is now enforced in code and covered by
tests.

- **Contract re-verified live before writing anything** (cheap re-probe, not a
  re-derivation): `robots.txt` still 3,564 bytes with six advertised sitemaps, no
  `Crawl-Delay` for `*`, and `/api/vindeenjob/` still `Disallow`ed
  (`RobotsRule.can_fetch` → False); keyword sitemap index still 4 children;
  `keyword-0.xml` still 10,000 URLs of which **2,251 are postcode-prefixed**;
  4 landing pages **4/4 HTTP 200**, 28 tiles each, `Online sinds` + contract
  label on 100% of tiles, 112 tiles → 55 unique ids. The **no-pagination
  contract was re-probed**: `?limit=100`, `?page=2` and `?start=15` each returned
  the identical 28 ids and `/2` answered 404, so the collector sends **no**
  pagination parameter at all. One drift: the `Server` header now reads
  `Kestrel` (was `envoy`); still no Cloudflare/Akamai/Incapsula header, no
  challenge.
- **`scrapers/reference_vdab.py`** (opt-in network, `make reference-vdab`,
  Increment 4's builder shape): enumerates postcodes from
  `api.basisregisters.vlaanderen.be/v2/postinfo?limit=500` across the `volgende`
  links, then reads `postinfo/{postcode}` for the `nuts3` field the list payload
  omits, validating every value against Eurostat GISCO `NUTS_AT_2024.csv`.
  Live build: **529 postcodes enumerated → 528 rows, 1 skipped (no `nuts3`),
  0 unmatched against GISCO**, 23 distinct NUTS 3 codes = **all 22 Flemish
  arrondissements** plus `BE100` for the single non-geographic postcode `0612`
  (unreachable from any landing-page slug). Brussels' `1000` answered
  `410 Verwijderde postcode`, as the gate predicted, and is absent. The walk is
  **restartable** (rows flushed every 50 postcodes, an existing CSV is resumed,
  `--fresh` starts over) and took ~9 minutes at the 1 s floor.
  `data/reference/vdab_postcode_nuts_2024.csv` + `reference_manifest_vdab.json`
  are committed so the offline gate keeps working.
- **`scrapers/vdab.py` (`VDABCollector`)** on the existing Collector Interface —
  `base.py`, `robots.py`, `retry.py`, `sanitize.py` and `validate.py` were reused
  unchanged:
  - **robots.txt is a gate, not a formality.** It is fetched and parsed once per
    sweep *before any other URL*, and `assert_allowed()` is called on **every**
    URL before it is requested; a disallowed URL raises `RobotsDisallowedError`
    instead of being skipped quietly. A `Crawl-Delay` longer than the configured
    pace would replace the pacer. Every sweep logs `api_path_allowed=False`,
    i.e. the live proof that the Angular API stays off-limits.
  - **Discovery** reads the keyword sitemap index and only as many child sitemaps
    as the page budget needs (`keyword-0.xml` alone yields **1,926**
    Flemish-postcode landing pages), filters to `<postcode>-<gemeente>` slugs and
    drops postcodes absent from the crosswalk (Brussels `1000`, foreign
    `1011-amsterdam`).
  - **Breadth ordering** (`order_by_postcode_breadth`): sitemap order is
    postcode-ascending with several slug variants per postcode, so a budgeted
    prefix would sample one corner of Flanders. Round-robining over postcodes
    puts one page per postcode first. Measured effect: **500 pages produced only
    5 duplicate ids** (0.04%) versus the canary's 26% overlap, and the sweep
    reached all 22 NUTS 3 codes.
  - **Allowlist-only parse** with BeautifulSoup + lxml (the lab's first HTML
    source): exactly two things are read per `div.product-tile` — the numeric id
    from the `/vindeenjob/vacatures/<id>/<slug>` href and the `Online sinds`
    label. The title, employer, city, description snippet, logo and tracking
    parameters in the same markup are never read; `VacancyTile(extra="forbid")`
    and `NormalizedRecord(extra="forbid")` are the backstops. Tiles without a
    resolvable id are counted, never given a fabricated identifier.
  - **Dutch date parser** (`parse_dutch_date`) covering all twelve abbreviations
    (`jan`…`dec`, including `mrt.`, `mei`, `okt.`) plus full names, total by
    construction: garbage, English, relative phrases (`vandaag`) and impossible
    dates (`31 feb.`) return `None` rather than a guess.
  - **SAFE_FIELDS:** `source=vdab`, `country=BE`, `lang`/`source_language=nl`,
    `number_of_vacancies=1`, `first_published` from the tile date,
    `last_modified=None`, `removed_at=None`, region from the pinned crosswalk,
    occupation `not_present` / `not_available_vdab_html` (there is no source
    occupation code at all — unlike Increment 4's `unmapped`, where `romeCode`
    existed).
  - **`last_modified` deliberately skipped.** The weekly vacancy sitemaps do
    carry a per-URL `<lastmod>`, but re-probing showed they are historic ISO-week
    slices (214 children from week 25/2024; the newest holds 872 URLs dated
    Feb/Mar 2026), so their ids largely do not intersect the current tiles. A
    join would cost 214 extra requests for a partial, sitemap-generation
    timestamp. Documented in the collector docstring, the feasibility row and
    every manifest's `coverage_limitations`.
- **Wiring:** `main.py` gains a typed `SourceConfig` for `vdab`/`be` (scope
  `be-flanders-all-active`, `reference_hashes` from the new crosswalk) and
  appends the live breadth/dedupe/coverage numbers to `coverage_limitations`;
  the Makefile gains `make scrape-vdab` and `make reference-vdab`. Nothing in
  the existing sources was restructured.
- **Tests: 45 new** (`tests/test_vdab.py`, `tests/test_vdab_crosswalk.py`), all
  respx-mocked against hand-written synthetic markup (no real employer, person or
  vacancy text in the repo): robots fetched first, every disallowed path raising,
  a sweep proving `/api/vindeenjob/` and `/rest/vindeenjob` are never requested,
  absent-robots allow-all, sitemap discovery + Flemish filtering + child-budget
  stop, breadth ordering, tile parsing, malformed/id-less tiles, missing totals,
  the full Dutch month table and garbage input, cross-page dedupe, page budget,
  a failed page breaking reconciliation on purpose, the "no pagination params"
  contract, the SAFE_FIELDS record shape, non-Flemish postcodes staying
  `unmapped`, crosswalk hit/miss/empty/missing-file, content-addressed reference
  hashes, HMAC determinism, PII isolation (record **and** intermediate
  `RawRecord`), 429 + transport-error retries and a fatal sitemap 500. The
  JobTech output-contract tests pass unchanged.
- **Live DoD sweep** `vdab/be-flanders-all-active/20260822T000000Z`:
  **500/500 landing pages, zero 4xx / zero non-200**, 12,287 tiles → **12,282
  rows** (5 duplicates dropped on HMAC `source_id`, 0 tiles without an id),
  `status=complete`, `expected_pages == completed_pages`,
  `expected_rows == row_count == NDJSON lines == 12,282`, 9.7 MB, ~10 minutes at
  1.2 s pacing. All source_ids unique 64-hex HMAC digests; region **`mapped` on
  100%** of rows across **all 22 Flemish NUTS 3 arrondissements** (largest BE241
  Halle-Vilvoorde 1,499); `first_published` on **100%** of rows (2011-02-28 …
  2026-08-22). PII scan of the raw NDJSON: **0 e-mails, 0 URLs, 0 `vindeenjob`
  strings, 0 postcodes** (checked against all 528 crosswalk postcodes outside the
  timestamp/id fields), exactly the 25 allowlist fields, and the only non-id
  string values are the enums, `NUTS-2024`, `nl`, `BE`, the 22 NUTS codes and
  their labels. The string `vdab` appears only as the mandatory `source` slug and
  in two method names — no brand content, employer name or logo, as the
  disclaimer's trademark clause requires.
- **Honest coverage gap, unpadded:** 12,282 rows is **5.3% of the advertised
  232,944** active Flemish vacancies. Each landing page renders at most its first
  28 tiles and has no pagination, so full coverage would need a large share of
  the 34,903 published landing pages (a multi-hour sweep). Stated in
  `coverage_limitations` on the manifest, in the roadmap status and in the
  feasibility row — not glossed as a snapshot.
- **Roadmap/feasibility updated:** Increment 5 marked **DONE 2026-08-22** with
  the DoD evidence; the feasibility row gains the mini-canary result, the built
  crosswalk row and a `DONE — live DoD evidence` row. Surface A stays **blocked**
  and unbuilt.

### 2026-08-23 - Increment 6 (NAV stillings-feed, Norway)

The lab's first **event-log** source, first **source-reported `removed_at`**, and
first source that populates **`esco_occupation_uri` from the source itself**. The
feasibility gate was opened and greened before any collector code was written.

- **Contract re-verified live before building** (a cheap re-probe of the
  2026-08-22 reconnaissance, not a re-derivation) — and it corrected NAV's own
  documentation twice:
  - `robots.txt` on `pam-stilling-feed.nav.no` is **absent** (404, a 156-byte
    Javalin JSON error body) ⇒ nothing disallowed; unauthenticated
    `GET /api/v1/feed` answers **401** with **no `WWW-Authenticate`** header, so
    the token plus the accepted ToS is the operative permission (the keyed-API
    reading from Increments 3–4; here robots is merely absent, which is strictly
    more permissive). Neighbouring hosts checked too:
    `arbeidsplassen.nav.no/robots.txt` is allow-all, `navikt.github.io` 404.
  - `GET /api/publicToken` → 200 `text/plain`, a 3-segment 287-character JWT.
  - Feed pages hold **exactly 1,000 items**; `next_url` is `/api/v1/feed/<uuid>`
    and `next_id` **equals the page's own ETag**; end-of-feed is `next_url` *and*
    `next_id` both `null` — reproduced live by seeking 20 minutes back (1 item,
    both null).
  - **Correction 1 (revalidation).** NAV's documented pseudocode sends
    `If-Modified-Since` *and* `If-None-Match` together. Measured: on a page URL,
    `If-None-Match` **alone** returns **304 with a 0-byte body**, while adding
    `If-Modified-Since` makes the API **re-seek** and return 200 (488,817 bytes);
    a stale ETag returns 200. The collector therefore sends `If-None-Match` only
    when revalidating and `If-Modified-Since` only when seeking. 304 is treated
    as *unchanged* — it is not a retry status and does not break reconciliation.
  - **Correction 2 (field name).** NAV's migration pseudocode references
    `_feed_entry.id`, which does not exist; the field is `uuid`. Confirmed and
    noted in the payload model.
  - `If-Modified-Since` genuinely **seeks** (a 2-day value started the feed at
    `2026-08-21T01:32`), and an unknown `feedentry` uuid answers **404 with an
    empty body**.
- **Measured, not assumed — INACTIVE details.** The docs distinguish an ad that
  is *"actively stopped"* (fields masked) from one merely inactive by expiry, so
  the share was measured on a fresh window: of **20 INACTIVE details, 18 returned
  111–112 bytes** with only `{uuid,status,sistEndret}` and **2 carried full
  `ad_content`** (10%). Decision from the measurement: **INACTIVE details are
  never fetched** — ~9 wasted paced requests per usable payload, and the fields an
  INACTIVE row needs (`removed_at`, region) are already on the feed event.
- **Measured — the ESCO win and its limit.** `ad_content.categoryList` carries
  three code systems on one ad (`ESCO`, `JANZZ`, `STYRK08`); the `ESCO` entry's
  code is an ESCO occupation URI, present on **12/12** sampled ACTIVE ads in the
  first probe. A second probe (29 ads) found **26 strict occupation URIs, 2 ads
  whose "ESCO" code was actually an ISCO-08 **group** URI**
  (`http://data.europa.eu/esco/isco/c9112`) and 1 ad with only JANZZ+STYRK08. An
  ISCO group is a coarser concept scheme, so it is **refused** for
  `esco_occupation_uri` and reported `unmapped` with its own method name
  (`nav_categorylist_esco_isco_group`) rather than as a parse failure — the first
  sweep showed this on ~15% of enriched rows, so naming it precisely matters.
- **`esco_occupation_label` stays `None`, with the reason recorded.** The source's
  `categoryList[].name` is Norwegian (`butikkmedarbeider`) and this project
  publishes **English** labels; the pinned
  `data/reference/jobtech_occupation_esco_1.2.1.csv` cannot help either — it is a
  JobTech→ESCO crosswalk with **Swedish** labels (3,891 rows), not the ESCO 1.2.1
  occupation universe. The URI is carried, the label is left to the publishing
  layer, and the crosswalk is used only as an independent sanity check (**216 of
  the 229 distinct URIs** in the first sweep also appear in it).
- **`scrapers/reference_nav.py`** (opt-in network, `make reference-nav`): Eurostat
  GISCO `NUTS_AT_2024.csv` (**17 Norwegian NUTS 3 codes**) × SSB Klass **104
  fylker** (16 codes = 15 counties + `99 Uoppgitt`) and **131 kommuner** (358 =
  357 + `9999 Uoppgitt`). A kommune code's first two digits are its fylke code,
  verified exhaustively: **0 orphan prefixes across all 358 codes** (`parentCode`
  is `null` in `codesAt.json`, so the prefix rule is the join). Unlike Increment
  5's 529-request walk this is **3 requests**, so no resume state was invented.
  - **The join is by name, and the names disagree on purpose.** SSB writes Sami
    duals with a spaced hyphen (`"Troms - Romsa - Tromssa"`), GISCO with slashes
    (`"Troms/Romsa/Tromssa"`), and the feed shouts (`"TRØNDELAG"`). One
    `normalize_region_name` — shared by the builder *and* the collector so the
    keys cannot drift — compares the Norwegian part case-, accent- and
    punctuation-insensitively while preserving inner hyphens (`Aurskog-Høland`,
    `Nord-Odal`).
  - **A trap the build surfaced:** SSB disambiguates repeated names with a
    parenthetical county (`"Herøy (Møre og Romsdal)"` / `"Herøy (Nordland)"`,
    `"Våler (Innlandet)"` / `"Våler (Østfold)"`) while the feed sends the bare
    `HERØY`. Keying on the qualified name would leave two rows the feed can never
    hit, so the qualifier is folded away — which makes the collision **visible**:
    those keys are written as `kommune-ambiguous` with **no code**, and the
    collector reports `ambiguous` instead of guessing a county.
  - Live build: **370 rows = 15 fylke + 353 kommune + 2 ambiguous**, **15/15
    fylker matched GISCO with 0 unexpected unmatched** (only `99 Uoppgitt`, which
    has no NUTS equivalent). `NO0B1` Jan Mayen and `NO0B2` Svalbard have no SSB
    fylke and are **reported in the manifest, never forced onto a county**.
    Historic kommune names were **deliberately excluded** (a pre-2020 kommune may
    have been split across two of today's counties, so its NUTS 3 would be a
    guess; ads are never active >6 months), and the resulting unmapped share is
    reported honestly — the feed does emit non-kommune strings (`"?"` appeared 23
    times on one page).
- **`scrapers/nav_norway.py` (`NAVFeedCollector`)** on the existing Collector
  Interface — `base.py`, `retry.py`, `sanitize.py`, `validate.py` reused
  unchanged; `RobotsDisallowedError` was **moved into `scrapers/robots.py`** so
  VDAB and NAV raise the *same* class instead of duplicating it:
  - **Event fold.** "Each change to an ad will generate a new entry in the feed,
    and the latest entry will contain the current state" — so events are folded
    per ad with last-event-wins, keyed on the **HMAC `source_id`**, never on the
    native uuid. Measured fold ratio: **~2.0 events per ad**.
  - **`removed_at` is source-reported** (the INACTIVE event's `sistEndret`), so
    the MPSV-style cross-sweep reconciliation pass is **not needed here** — stated
    in the docstring so nobody adds one out of habit. A re-activated ad
    (INACTIVE→ACTIVE) correctly ends up with `removed_at = None`.
  - **Token handling.** `NAV_FEED_TOKEN` (private consumer token) from env/`.env`
    wins; otherwise the public token is used and **cached in gitignored
    `data/state/nav_public_token.json`** (it is published at a public URL, rotates
    "at irregular intervals", and its endpoint measured 26–28 s under load, so
    caching means one request per rotation instead of one per sweep). A 401
    refreshes once and replays. No token is committed, printed or logged — only
    its length and segment count.
  - **Poll cursor** in gitignored `data/state/nav_feed_cursor.json` (page id from
    the page's own `feed_url`, its ETag, `Last-Modified`, `next_url`), so a poll
    resumes at `next_url` when the previous sweep stopped mid-feed and otherwise
    revalidates the tail with `If-None-Match`. The bare `/api/v1/feed` seek URL is
    never stored, because without `If-Modified-Since` it restarts at 2019.
  - **Details are budgeted and optional.** `--max-details` bounds them (one paced
    request each ⇒ the sweep's wall-clock dial), they are spent in HMAC order so a
    partial budget is a window-wide sample rather than the oldest N events, and a
    404 or persistent 5xx on a detail is **counted and skipped, not fatal** — a
    feed-page failure stays fatal, because a lost page is lost events.
  - **Region** resolves county → municipality → `_feed_entry.municipal`
    (`low_confidence`: a single denormalized header field that cannot be
    cross-checked and is all a masked ad has), with locations that disagree →
    `ambiguous`, a workplace outside Norway → `unmapped`, and NAV's `"?"`
    placeholder → `unmapped` rather than `not_present` (a field *was* sent).
  - **PII:** the payload models declare only allowlist-relevant fields
    (`extra="ignore"`), so `contactList`, `employer`/`orgnr`, the 3.7 kB
    `description`, `title`/`jobtitle`, `applicationUrl`/`sourceurl`/`link` and
    `address`/`city`/`postalCode` never reach `parse()`; `RawRecord.payload`
    carries **model dumps only**, and `NormalizedRecord(extra="forbid")` is the
    backstop.
- **A real NAV-side incident, handled the charter's way.** Between ~01:20 and
  ~14:40 the host degraded intermittently: `/api/publicToken` answered in **26–28
  s**, the feed returned **500** and **504** and read-timed-out at 60–90 s. The
  response was to **back off** (five- to fifteen-minute waits, single-request
  health checks) rather than retry harder, and to harden the collector for what
  was measured: a **90 s** timeout (the lab's 30 s default expired mid-sweep), the
  cached token, and 5xx-tolerant detail fetches. The host recovered fully and the
  DoD sweeps then ran clean.
- **Wiring:** `main.py` gains a typed `SourceConfig` for `nav`/`no` (scope
  `no-all-events`, deliberately stable across daily polls — the window and budgets
  live in `coverage_limitations`, not in `scope_params`, so `scope_hash` does not
  move), plus `--since`, `--max-details` and `--fresh`; the Makefile gains
  `make scrape-nav` and `make reference-nav` with an honest runtime comment.
  Nothing in the existing sources was restructured.
- **Tests: 93 new** (`tests/test_nav_norway.py`, `tests/test_nav_crosswalk.py`),
  all respx-mocked against hand-written synthetic payloads (no real employer,
  person or ad text in the repo): both token routes (env and `.env`), the disk
  cache reused across sweeps, 401 → refresh once → replay, a second 401 as a real
  error, robots fetched before any other URL and enforced per URL, `next_url`
  pagination to a null `next_id`, the seek carrying `If-Modified-Since` only,
  **304 treated as unchanged with a reconciled zero-row manifest**, cursor resume
  from `next_url`, an explicit `--since` overriding the cursor, a corrupt cursor
  ignored, event folding in both orderings (ACTIVE→INACTIVE stamps `removed_at`,
  INACTIVE→ACTIVE does not), folding keyed on the HMAC digest, INACTIVE ads never
  costing a detail request, content-masked details, a detail 404 and a persistent
  detail 5xx counted-not-fatal, a 403 still fatal, the detail budget bounding
  requests but not rows, `positioncount` coercion (11 cases incl. garbage and
  negatives), ESCO extraction (single/multiple/tie/ISCO-group/unrecognized/empty/
  absent), region resolution across all six outcomes, the `"?"` placeholder as
  `unmapped`, name folding across SSB/GISCO/feed spellings, PII isolation on the
  record **and** the intermediate `RawRecord`, 429 with `Retry-After`, a transport
  error, a malformed page failing loudly, and the crosswalk builder's joins and
  loud failures. The JobTech output-contract tests pass unchanged.
- **Live DoD sweeps** (serial, ≥1 s pacing, zero 4xx):
  - **Backfill** `nav/no-all-events/20260822T000000Z` (`--since 12 --max-pages 20
    --max-details 1500 --fresh`): **20/20 pages, 20,000 events folded to 10,342
    rows**, `status=complete`, `expected_pages == completed_pages`,
    `expected_rows == row_count == NDJSON lines == 10,342`, 8.8 MB, ~26 min. All
    source_ids unique 64-hex HMAC. **5,208 ACTIVE / 5,134 INACTIVE, with all
    5,134 INACTIVE rows carrying a source-reported `removed_at`.** 1,500 details
    → 1,434 with `ad_content`, 66 content-masked, 0 missing, 0 abandoned. Region
    on **10,159 rows (98.2%)** across **all 15 mainland NUTS 3 regions**
    (`region_mapping_status` populated on 100%); ESCO URI on **1,172 rows =
    81.7% of the detail-enriched rows** (11.3% of all rows — the detail budget's
    honest consequence), 261 distinct URIs of which **250 also appear in the
    pinned JobTech→ESCO crosswalk**, and 230 rows `unmapped` because the "ESCO"
    code was an ISCO-08 group URI.
  - **Poll cycle** `nav/no-all-events/20260823T000000Z` (`--max-details 700`, no
    `--since`): **resumed from the persisted cursor**, 6/6 pages, 4,600 events →
    **2,239 rows**, reconciled, 1.9 MB, and **reached the true end of the feed
    live** (`next_url` and `next_id` both null). 1,012 source-reported
    `removed_at`; 553 ESCO URIs (79.0% of enriched rows); region on 2,201 rows
    (98.3%); **0 token requests** — it reused the token the backfill had cached.
  - **Token rotation proven live, not just mocked:** the cached public token had
    rotated during the overnight incident, so the backfill's first authorized
    request answered 401; the collector refreshed once and replayed, and the walk
    continued with no lost page and no aborted sweep (`token_requests=1`,
    `token_refreshes=1`, visible in the manifest's `coverage_limitations`).
  - **Combined: 12,581 rows over 12,051 distinct ads**, 530 ads present in both
    segments (23.7% of poll rows — they had events in both, which is exactly what
    an event log should show), **6,146 source-reported `removed_at`**, 1,725 ESCO
    URIs. **PII scan of both NDJSON files: clean** — 0 e-mails, 0 URLs other than
    ESCO occupation URIs, 0 phone-like, 0 orgnr-like, 0 postcode-like values,
    exactly the 25 allowlist fields, no native uuid anywhere.
  - **Two process notes, recorded rather than smoothed over.** The roadmap's
    "≤100 records" canary size **cannot be expressed against this source** (the
    server's page size is fixed at 1,000 and there is no smaller unit), so the
    pre-DoD validation was a completed 3-day backfill through the collector
    (8/8 pages, 3,615 rows, zero 4xx, reconciled); its partition was later
    overwritten by the wider DoD backfill under the same `sweep_id`. Separately,
    two poll runs were killed by an environment-level process reap **after** the
    feed walk but **before** the partition write; the final poll was therefore run
    in the foreground, resuming from a cursor reconstructed read-only by
    re-walking the same 20 pages (the feed is append-only, so page ids are
    stable).
- **Honest coverage bound, unpadded:** a sweep is a **window over an append-only
  event log**, never a snapshot. Coverage is bounded by the `--since` window, by
  the `--max-details` budget (each detail is one paced request, so ~1 s per
  enriched row — which is why only 11.3% of backfill rows carry an ESCO URI even
  though 81.7% of *enriched* rows do), and by Finn.no's documented absence from
  the API. NAV publishes **no advertised active-ad total**, so no completeness
  percentage is claimed or invented. All of this is in `coverage_limitations` on
  every manifest.
- **Roadmap/feasibility updated:** Increment 6 marked **DONE 2026-08-23** with the
  DoD evidence; the feasibility row gains the built-crosswalk row, the validation
  run, the host-incident record and a `DONE — live DoD evidence` row.

### 2026-08-23 - Increment 7 (Työmarkkinatori / Job Market Finland, FI) — collector built, DoD blocked

- **Order followed.** SCRAPERS.md -> SCRAPER_ROADMAP.md -> SCRAPER_SOURCE_LANDSCAPE.md
  -> SCRAPER_FEASIBILITY.md -> SESSIONS.md, then the feasibility gate **before**
  any code, then reuse of `base.py` / `robots.py` / `retry.py` / `sanitize.py` /
  `validate.py` with no new compliance helper and no restructuring of `main.py`
  or the Makefile.
- **The gate was opened first, and it changed the build three times.**
  1. **`tyomarkkinatori.fi/robots.txt` disallows `/api/`** (and `/*/api/`),
     verified with the lab's own `RobotsRule`. That is exactly where the source's
     `KUNTA` / `MAAKUNTA` / `ESCO_AMMATTI` / `ESCO_OSAAMINEN` codesets live, so
     they were **not fetched — not even once** (the VDAB `/api/vindeenjob/`
     precedent). The region crosswalk was built from **Statistics Finland**
     instead, which turned out to be the better authority anyway. Docs, the
     OpenAPI description and `/dam/` are all robots-**allowed** and were used.
  2. **The Kipa gateway is IP-allowlisted, not just key-gated.** `api.ahtp.fi`
     and `api-qa.ahtp.fi` both fail the TCP handshake on 443 (**21.0 s / 21.1 s
     timeouts**, ICMP to `13.81.203.220` succeeds) while the sibling
     `sahkoinenasiointi.ahtp.fi` answers **200 in 0.52 s** — so this is a
     host-level filter, not an egress problem and not an outage, exactly as the
     technical doc says (*"the credentials … **and the IP addresses openings** are
     provided by the KEHA Center"*). Consequence: **no public sandbox exists**,
     QA included, so the contract was pinned from the **published OpenAPI
     description** (`P67-tmt-provider-haku-V2`, 19,115 bytes) and every branch is
     respx-mocked rather than measured. Every contract claim in the docstring and
     the feasibility row is labelled as contract-derived.
  3. **The API has no pagination, no cursor and no terminal sentinel.**
     `FiltersV2` carries only `onlyStatus` (`PUBLISHED`/`ARCHIVED`), five
     `{from, to}` intervals (`created`/`modified`/`published`/`archived`/
     `expires`) and eight set filters — no offset, limit, page or continuation
     field. One POST returns one whole result set as `application/x-ndjson` and
     the stream ends when the body ends. So the "cursor" the prompt asked about is
     a **client-side watermark**: the maximum `metadata.lastModified` seen,
     persisted to `data/state/finland_tmt_cursor.json` and replayed as
     `modified.from`. A `PUBLISHED` watermark is deliberately **not** reused for
     an `ARCHIVED` pass, and a `--max-rows`-truncated sample **does not** advance
     it.
- **Onboarding: NOT STARTED, on purpose, and said plainly.** The activation
  notification is an organisation-level commitment whose access right is *"sidottu
  rajapinnan käyttäjän Y-tunnukseen"* (bound to the API user's Finnish business
  id), with a KEHA suitability check and contact-person personal data under §5 of
  the terms. This lab is not a Finnish registered organisation, so the Webropol
  form was **not submitted** — filing it would have meant committing a
  non-existent organisation to the Terms of Use. That is materially different from
  Increment 4 (self-service click-through) and Increment 6 (public experimentation
  token), and it is recorded as *not started with a reason*, never as "pending".
  **No key is held; no credential or token is in the repository.**
- **ToS reviewed in full** (`…/terms-of-use-for-job-market-finlands-job-posting-apis`,
  updated 12.3.2026). Verdict **restricted, not prohibited**: automated access *is*
  the mechanism, but the named purpose is displaying postings in the API user's own
  service and **no statistical/analytical purpose is named** (unlike NAV). Four
  conditions were answered structurally rather than noted and forgotten:
  attribution (*"Source: Job Market Finland's customer information system"*, now
  the manifest's `licence_reference`), no forwarding to third parties (nothing
  forwardable is produced), *"removed job postings cannot be stored so that they
  can still be retrieved"* (the output holds **no posting content at all** and
  stamps the source's own `metadata.archived` as `removed_at`), and no marketing
  use of the dataset.
- **Built.** `scrapers/finland_tmt.py` (`FinlandTMTCollector`): robots fetched and
  asserted per URL before the first request, 1 s pacing floor with `Crawl-delay`
  adoption, `KIPA-Subscription-Key` on every call plus an optional bearer with
  **401 refresh-once-and-replay**, a streaming POST whose retryable responses are
  drained and closed before `scrapers.retry` retries them (so a 429/5xx retry
  never leaks a connection), `RateLimit-Limit/Remaining/Reset` logged per
  response, allowlist-only `extra="ignore"` models, and `--max-rows` as the
  smoke-pull dial. Failure semantics are deliberate: a **corrupt JSON line** is
  counted and skipped, a **structurally wrong** line raises through pydantic, and
  a stream that yields lines but **no usable row raises rather than writing an
  empty partition** (the silent-success trap the manifest reconciliation would
  otherwise pass).
- **Two lab firsts.** This is the first source to populate **`skill_mappings`**
  (from `position.skills`, in the element shape
  `transform/models/staging/stg_skill_mappings.sql` reads, one element per skill
  in source order) and the second with a **source-reported `removed_at`**. The
  FINESCO trap was measured, not assumed: the source's own published distribution
  (`definitions.zip`, 14,062,560 bytes, `version.txt` = **FINESCO 1.2.0-R8**) holds
  **3,046** ESCO occupation URIs but also **619** ISCO group URIs and **78 Finnish
  national extensions** under `data.tyomarkkinatori.fi`, plus **220** ISCED-F
  concepts among 15,163 skills. So values are classified into five honest
  outcomes — ESCO -> `mapped`, ISCO group -> `low_confidence` with **no URI
  written**, national extension -> `unmapped`, unrecognised -> `unmapped`, absent
  -> `not_present` — and `occupation_mapping_confidence` stays `None` because the
  source attaches no score (inventing "high" would be an overclaim).
  `esco_occupation_label` stays `None` for the Increment 6 reason.
- **Region fully mapped, 0 unmatched.** `scrapers/reference_finland.py` +
  `data/reference/finland_tmt_region_nuts_2024.csv` (**327 rows** = 308 `kunta` +
  19 `maakunta` + **0 `maakunta-ambiguous`**), built live in 3 paced requests.
  Statistics Finland's `kunta_1_20260101#nuts_2_20260101` key names itself
  *"virallinen NUTS 2024"* and returns **924 maps = 308 municipalities × NUTS
  levels 1/2/3**; the 308 level-3 maps cover **all 19** Finnish NUTS 3 codes with
  **0 absent from Eurostat GISCO NUTS 2024 and 0 GISCO codes without a
  municipality** (bijective). The maakunta layer is **derived then verified**: 19
  regions each resolving to exactly one NUTS 3 code, which is the empirical proof
  that a Finnish maakunta *is* a NUTS 3 region. **No name join was needed** — a
  relief, because the label mismatches that would have broken one are real
  (Uusimaa vs Helsinki-Uusimaa, Ahvenanmaa vs Åland). One normalizer
  (`normalize_kunta_code` / `normalize_maakunta_code`) is shared by the builder and
  the collector so the keys cannot drift, and a maakunta that ever spanned two
  NUTS 3 codes would be written **with no code** so the collector reports
  `ambiguous` instead of guessing (tested).
- **DoD: NOT MET, and not dressed up.** Roadmap DoD is *"streamed pull of active
  postings ≥5,000 records with ESCO occupation/skill URIs populated; no 4xx/401
  after credentials issued"*. **0 records were retrieved.** Evidence: without a key
  the CLI **raises before opening a socket**; with a placeholder key it makes
  exactly one host contact — `robots.txt`, which needs no credential — and after 4
  retried attempts over **94.3 s** raises *"cannot reach
  https://api.ahtp.fi/robots.txt: the Kipa gateway is IP-allowlisted"*. **No
  authenticated request was sent, no partition and no watermark file were written**
  (`data/raw/collections/` still has no `tmt/`), so nothing empty is presented as a
  sweep. Increment 7 is recorded **BLOCKED (build complete, DoD pending KEHA
  activation)**, not DONE.
- **Three assumptions flagged for the first authorised sweep** rather than buried:
  which auth header the gateway actually enforces (the technical doc says
  `KIPA-Subscription-Key`, the OpenAPI declares `bearerAuth` for the backend
  behind it — the collector sends both when a bearer exists), whether timestamps
  are naive (every `date-time` is `maxLength 26`, exactly
  `YYYY-MM-DDTHH:MM:SS.ffffff` with no room for a designator, so a naive value is
  read as UTC), and the real rate-limit numbers (headers exist, values are
  unpublished).
- **Wiring and gate.** `main.py` gained a `SourceConfig` entry (slug `tmt`, scope
  `fi-all-active`, aliases `fi`/`tmt`/`finland`, reference hash from the new
  crosswalk, live counters appended to `coverage_limitations`) and the flags
  `--max-rows` / `--status`, with `--max-pages` **rejected** for this source
  because P67 has no pages; the Makefile gained `scrape-finland` and
  `reference-finland` with honest runtime comments naming the credential and
  IP-opening preconditions. **`make check` green: 367 tests** (313 before), ruff
  clean, mypy strict clean; the JobTech output-contract tests pass unchanged.
### 2026-08-23 - P1 (Germany active-lane architecture) — planning, no code

- **Why:** Germany is the highest-value market and the least covered (Adzuna DE
  4,841 of ~1.16M advertised = **0.4%**). The user re-ordered the roadmap to make
  Germany the active build target. This session produced the architecture, ran
  the live probes that shape it, and recorded the reorder — it built nothing.
- **Live probes (all at the 1 s floor, single honest UA):** robots.txt for
  kimeta.de (6,257 B), joblift.de (**403 CloudFront**), stellenanzeigen.de
  (772 B after the www redirect), arbeitsagentur.de (208 B, allow-all),
  govdata.de (blanket `*` deny — excluded as a reference source), destatis.de
  (allow, `Crawl-delay: 30`), gdz.bkg.bund.de (only GPTBot blocked), plus the
  Joblift partner-API page (`/business-developer`, **also 403 CloudFront**).
  Parsed kimeta/stellenanzeigen/arbeitsagentur with the lab's own `RobotsRule`.
- **Three findings that re-ordered the grey chain:**
  1. **Kimeta is robots-blocked for this lab.** `User-agent: *` → `Disallow: /`.
     `RobotsRule` confirms DENY on `/jobs/berlin`, `/search`, `/api/job-pdf`.
     There is no keyed-API reading to rescue it (that reading applies to Adzuna's
     API host, not a public HTML site). Expected gate verdict: **blocked** — the
     roadmap's Inc 8 becomes the *tertiary* German source, not the first.
  2. **Joblift is CloudFront-403 at the edge** — even robots.txt is blocked from
     this egress, and so is its official partner-API page. Its homepage (fetched
     via search cache) advertises Berlin 24,296 / Köln 27,064 / München 20,249 /
     Einzelhandel 96,881 vacancies and openly lists StepStone, Monster and
     stellenanzeigen as indexed boards. The gate must distinguish a UA-based
     block (maybe honestly passable) from an egress/WAF block (not).
  3. **Stellenanzeigen.de is robots-permitted** (`/job/*`, `/suche/*` ALLOW;
     `/stabi/` etc. DENY), advertises **three sitemaps**, and community scrapers
     (Apify actors, cited as *reference only* — their proxy/TLS-fingerprint
     stacks are not lab practice) confirm `JobPosting` JSON-LD on detail pages
     and "passive Cloudflare, no active challenge". It becomes the **primary
     German build** and moves first in the serial chain: **10 → 9 → 8**.
- **New prerequisite found and scheduled:** every German source needs a
  location → NUTS 3 2024 mapping and none ships one. Germany has **400 NUTS 3
  codes** (GISCO NUTS 2024, verified). Authority confirmed: BKG Geodatenzentrum
  (robots-permitted) Orts-/Gemeindeverzeichnis (PLZ + AGS) cross-checked with
  destatis, validated against GISCO — the German analogue of SSB Klass /
  Statistics Finland. Deliverable `scrapers/reference_germany.py` +
  `germany_plz_nuts_2024.csv`, 0-unmatched bar, built before any HTML collector.
- **Access tracks (parallel, no scraper):** BA Jobsuche (HR-BA-XML / explicit
  arrangement — the only full-coverage route; the portal's allow-all robots does
  not extend to the Jobsuche data) and the EURES arrangement (ESCO-native,
  carries the German PES feed). Their status is recorded, never assumed.
- **Foolproof mechanisms codified per source:** gate before build (robots on
  every host via `RobotsRule`, ToS verbatim, rate limits, snapshot semantics,
  PII, exclusions) → canary (≤100, 1 s+, serial-only) → mini-canary before the
  sweep → manifest reconciliation → PII scan → NAV-style incident hardening →
  honest coverage bound in every manifest. Backup chain is predetermined, not
  improvised under pressure (see the roadmap's Germany section).
- **Cross-source overlap stated, not hidden:** aggregators share boards; the
  SAFE_FIELDS contract carries no join key, so cross-source dedupe is
  impossible at collection and is deliberately left to downstream analytics.
  Every manifest states its own window against the advertised stock.
- **Records:** `SCRAPER_ROADMAP.md` gained the "Germany — ACTIVE LANE" section
  (coverage stack, re-ordered chain, new prerequisite, access tracks, execution
  order) and a rewritten Parallelization section; the Risk Matrix rows 7–10
  were corrected to the measured evidence; `SCRAPER_FEASIBILITY.md` gained the
  "Germany programme" per-surface status table; this session log row. Next
  sessions: Stellenanzeigen gate-only → `reference_germany.py` → Stellenanzeigen
  canary + collector + DoD sweep → Joblift gate → Kimeta gate.
### 2026-08-23 - P2 (Germany re-assessment under the relaxed constraint) — no code

- **Constraint change (user decision):** the ToS/robots gate is **relaxed for
  this private research/educational student project**. Robots and ToS are still
  recorded as evidence in the feasibility rows but no longer block a build. The
  gates that survive: technical anti-bot (Cloudflare/DataDome/Akamai/WAF), the
  litigation risk on Indeed, the 1 s pacing floor, the PII ban, HMAC
  pseudonymization, canaries (as a technical check), and manifest reconciliation.
- **The plan's #1 changed.** Live probes (22:00 UTC, at the 1 s floor) found the
  **BA Jobsuche public website** is server-rendered, plain-HTTP accessible, and
  free of anti-bot: `www.arbeitsagentur.de/jobsuche/suche?was=…&wo=…` returned
  200 / 370 KB with job titles, employers, publish dates, location+distance,
  salary, employment type, homeoffice and native ref IDs
  (`Stellenangebot 10000-1202838080-S`); the search host serves no robots.txt
  (404). That is ~1.9M postings — the single biggest German prize, previously
  classified as "agreement-only / never scraped". The internal REST API
  (`rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs`, found in
  `config/config.js`) is **WAF-403 even from a browser** (verified with Playwright
  from the same-origin SPA), so the collector is an HTML parser, not an API client.
- **Also verified plain-HTTP accessible with a browser UA:** **StepStone.de**
  (search 200 / 1.1 MB, `application/ld+json`, no Akamai challenge on search
  pages), **Indeed.de** (200 / 1.3 MB, `data-jk` ids — **litigation history
  flagged, decision required**), **Kimeta** (homepage 200 / 214 KB; JS-driven
  app, no technical anti-bot). **Stellenanzeigen.de** remains robots-permitted
  with JSON-LD and passive Cloudflare (smaller volume).
- **Confirmed technically blocked:** **Monster.de** (DataDome challenge even on
  robots.txt — `geo.captcha-delivery.com`), **Joblift** (CloudFront 403 on
  robots.txt AND its `/business-developer` partner-API page; needs a real-browser
  test), **Interamt** (curl loops 50 redirects, JS-only SPA). These become
  "probe/blocked" rows needing a tooling decision (browser automation), not
  immediate builds.
- **Plan recorded:** roadmap gained the tiered German stack (BA Jobsuche →
  StepStone → Indeed → Kimeta → Stellenanzeigen → Joblift/Monster/Interamt probes
  → Arbeitnow fill) with the technical-feasibility-first execution order; the
  feasibility doc's Germany programme table was rewritten from legal verdicts to
  technical ones; the landscape's German measured-facts paragraph updated; risk
  matrix rows 8-10 re-scored and G1-G4 rows added. The German region crosswalk
  (`reference_germany.py`, BKG × GISCO, 400 NUTS 3 codes) remains the build
  prerequisite. Next session: `reference_germany.py`, then the BA Jobsuche
  feasibility gate and collector.

### 2026-08-24 — Increment 8 (BA Jobsuche Germany #1 build)

**Deliverable 1 — German region crosswalk:**

Built `scrapers/reference_germany.py` + `data/reference/germany_plz_nuts_2024.csv`
+ `reference_manifest_germany.json`. Three-authority chain: **destatis Kreise
table** (AGS-Kreis 5-digit → NUTS 2024, the official key, covers 400/400 GISCO
codes) × **BKG VZ250_GEM** (Orts-/Gemeindeverzeichnis, 11,001 municipalities
with AGS + Kreis, `dl-de/by-2-0`) × **destatis Anschriftenverzeichnis** (10,749
municipalities with Zustell-PLZ). Pinned CSV: 22,140 rows (4,862 PLZ + 11,000
municipality + 400 Kreis), 400/400 NUTS 3 codes, 0 unmatched, 121 Thuringian
VZ250 stale-NUTS deviations recorded. 11 PLZ codes span >1 NUTS 3 (ambiguous),
397 municipality names in >1 NUTS 3 (ambiguous). `make reference-germany` target
added. First commit: `e8c0553` (feat). Second commit: `810d057` (fix — the BKG
VZ250_GEM `.dbf` stores names as UTF-8; the builder decoded them as latin-1,
double-encoding umlauts in the pinned CSV; rebuilt).

**Deliverable 2 — BA Jobsuche feasibility gate + collector:**

Live probes of the public SSR search interface (25 items/page, `&page=N`
pagination, 400-page = 10,000-listing window, 403 Apache-edge throttle after
~50 requests, recovers after ~30 s idle). Full feasibility row added to
`SCRAPER_FEASIBILITY.md`.

`scrapers/ba_jobsuche.py`: BAJobsucheCollector — SSR HTML parser, allowlist-only
(ref ID + date + city only), robots-as-evidence (disallow logs, 403 stops),
city→NUTS 3 via German crosswalk (mapped/ambiguous/unmapped), 403 handled as
rate-limit with 45 s cooldown-then-retry (Apache edge token bucket), HMAC
dedupe, 25 items/page, 400-page window (10,000 max). `main.py` SourceConfig
slug `ba` with `--source ba` / `--source ba_jobsuche` / `--source de`. 22 new
respx tests for parsing, crosswalk, robots, PII, dedupe, 429, schema drift,
page budget.

**DoD verification (foreground, serial, ≥1 s pacing):**

Sweep 400/400 pages, 10,000 rows, `status=complete`, `expected_pages ==
completed_pages == 400`, `expected_rows == row_count == 10,000 NDJSON lines`,
zero 4xx, 10,000 unique 64-hex HMAC source_ids, 100% first_published coverage,
358/400 distinct NUTS 3 codes mapped (6,448 mapped, 3,497 unmapped, 55
ambiguous), zero PII. 7 throttle events absorbed (45 s cooldown each). Honest
bound: 10,000-listing per-query window, plus ~50-request burst throttle.

**make check:** 389 tests passed (367 + 22), ruff + mypy strict + pytest green.

### 2026-08-24 — P3 (EU coverage + main-app push-readiness assessment) — no code

Prep step for the Increment 9 segmented-DE build: measured what the lab has
collected so far and whether it can be pushed into the main app.

**Rows per EU country across all collection partitions (11 partitions, 7 sources):**

| Country | Sources | Sweeps | Rows (all) | Distinct postings |
| --- | --- | --- | --- | --- |
| BE | vdab | 1 | 12,282 | 12,282 |
| CZ | mpsv | 2 | 77,806 | 38,903 |
| DE | adzuna, ba | 2 | 14,841 | 14,841 |
| FR | francetravail | 2 | 234,861 | 217,680 |
| NL | adzuna | 1 | 4,956 | 4,956 |
| NO | nav | 2 | 12,581 | 12,051 |
| PL | cbop | 1 | 22,068 | 22,068 |
| **Total** | | 11 | **379,395** | **≈322.8k** |

Every partition is `status=complete` with `expected_pages == completed_pages`
and `expected_rows == row_count == NDJSON lines` (verified per file, not trusted
from the manifest alone).

**Advertised-vs-collected coverage (latest sweep against the advertised total
recorded in the same manifest):**

| Country | Source | Collected | Advertised | Coverage |
| --- | --- | --- | --- | --- |
| CZ | mpsv | 38,903 | full active-set dump | **~100%** (the dump IS the dataset) |
| PL | cbop | 22,068 | 22,068 active | **100%** |
| FR | francetravail | 217,455 | 503,269 | **43.2%** |
| BE | vdab | 12,282 | 232,944 | **5.3%** (28 tiles/page, no pagination) |
| NL | adzuna | 4,956 | 190,607 | **2.6%** |
| DE | ba | 10,000 | 10,000-listing window | **100% of window / ~0.5% of ~1.9M stock** |
| DE | adzuna | 4,841 | 1,155,948 | **0.4%** |
| NO | nav | 2,239 (window) | none published | n/a (event log, not a snapshot) |

**Sufficiency for a main app push:**

1. **Schema — byte-compatible, no code change needed.** Lab `observations.ndjson`
   fields match the main app's `stg_postings.sql` column map exactly (including
   the Increment-14 dimension keys), and manifests match
   `stg_collection_manifests.sql`. The main app reads both via
   `MANIFESTS_PATH`/`OBSERVATIONS_PATH` env vars and joins on
   `source/scope_id/sweep_id/observed_at`, which align in every lab partition.
2. **The single gate blocker is `accepted_values: [DE, SE]` on
   `stg_postings.country` (`transform/models/staging/schema.yml:66`).** DE is
   already eligible; SE is the main project's own JobTech lane. BE, CZ, FR, NL,
   NO, PL (≈309k of 379k rows) would fail `dbt test` until the main checkout
   widens the list — that is a main-project decision, explicitly out of this
   lab's remit (plan §10, charter golden rule 8).
3. **DE is pipeline-ready but not coverage-sufficient.** 14,841 distinct DE rows
   ≈ 0.5% of the ~1.9M advertised stock; BA region mapping is 64.5% mapped
   (6,448/10,000) with 358/400 NUTS 3 codes, and Adzuna DE is region
   `not_present`. A DE-only push would pass the dbt gate today but is a windowed
   sample with no coverage claim. The Increment 9 DoD (≥100,000 distinct DE
   rows, ≥80% region mapped, ≥380/400 NUTS 3 codes) is the correct readiness
   bar before "sufficient" is claimed.
4. **Data trees are separate checkouts.** The main app reads its own
   `data/raw/collections/jobtech/`; a push is an ingestion-side operation
   (env-var override or copying partitions into the main tree), not a lab code
   change.

### 2026-08-24 — Increment 9 (BA Jobsuche segmented regional census) — code + live

**Gate probes (~40 paced requests, live, zero 4xx):** verified the segment axes
that the plan's predecessor assumed. The critical finding: **`wo=Landkreis+…`
queries are broken** — `Landkreis+Kiel`, `Landkreis+München`, `Landkreis+Starnberg`,
`Landkreis+Teltow-Fläming`, `Landkreis+Konstanz`, `Landkreis+Karlsruhe` all return
the **same 7 postings labelled "Rosenheim"**. Compound `-Kreis` names also fail
(`Rhein-Sieg-Kreis` → 25 Rüdesheim am Rhein items, wrong region). So the
level-2 backbone is **municipality names + PLZ codes** from the crosswalk, not
Kreis names. `umkreis=0` confirmed tight (different result set from the default
radius) ⇒ **Tier 3 = `mapped`**. `veroeffentlichtseit` filter works (controlled
A/B with different refs). No server-rendered total. Non-existent locations
return empty (no silent national fallback). Crosswalk analysis: 10,085 unique
municipality names (single NUTS 3), 397 ambiguous (all resolve via PLZ, each
PLZ → single NUTS 3), 400/400 NUTS 3 covered by PLZ rows.

**Code delivered:**
- `scrapers/ba_segments.py` — Segment model, SegmentFrontier (keyed by
  `(level, key)` to avoid Bundesland/municipality key collisions), `pending()`
  with breadth-first region ordering (level 2 → level 0 → level 1 → level 3 →
  level 4), `build_initial_frontier()` (16 Bundesländer, 3 city-states
  pre-subdivided, 10,761 level-2 segments).
- `scrapers/ba_jobsuche.py` — `BA_NON_GEOGRAPHIC_MARKERS` → `ambiguous`,
  `BA_NUTS1_ALIASES` (qualifier→NUTS-1 prefix), `normalize_location()` shared
  helper (Tier 1 qualifier strip/alias, Tier 2 segment-context disambiguation,
  non-geographic → `ambiguous`); `GermanCrosswalk` extended with
  `candidates_for_name()`, `municipality_names_by_nuts3()`,
  `plz_rows_for_name()`, `plz_codes_for_nuts()`, `resolve_by_city_segmented()`;
  `BAJobsucheCollector` extended with segmented mode (frontier, segment oracle,
  truncation probe, subdivide, `_walk_segment`, `_fetch_segmented`); Tier 3
  applied in `normalize()` when `segment_nuts3` present and `umkreis=0` →
  `mapped/ba_segment_provenance_nuts3`, radius → `low_confidence`.
- `main.py` — `--segmented/--max-segments/--min-level/--umkreis` flags,
  `_ba_jobsuche_segmented()` factory, per-chunk timestamped sweep_id to avoid
  partition overwrite on resume.
- `Makefile` — `scrape-ba-segmented` / `check-ba-segmented`.
- `tests/test_ba_segments.py` — 21 new respx tests (oracle, subdivision,
  tiers, frontier, budget, dedupe, throttle, schema drift, PII, city-states).
- `scripts/check_ba_segmented_readiness.py` — §9 DoD proof: loads all
  `de-stock-segmented` partitions, reconciles manifests, asserts ≥85% mapped,
  ≥390/400 NUTS 3, ≤5% unmapped, per-tier breakdown.
- `SCRAPER_FEASIBILITY.md` — "BA Jobsuche — segmented stock" sub-row with all
  probe results and the locked segment-key strategy.

**Live evidence (two sessions, 63 bounded chunks of `--max-segments 40`):**
65 partitions under `de-stock-segmented`, every one `status=complete` with
matching `expected_pages == completed_pages` and `expected_rows == row_count`;
**203,674 distinct rows** (deduped on HMAC source_id across partitions),
**mapped 203,215 (99.77%), ambiguous 459 (the non-geographic markers —
`Verschiedene Arbeitsorte` / `Deutschland` / `Bundesweit` — classified
`ba_location_multiple`/`ba_location_nationwide`), unmapped 0, low_confidence 0**.
**Per-tier breakdown: Tier 1 186,761 (city crosswalk + qualifier), Tier 2 2,284
(segment-context disambiguation), Tier 3 14,170 (segment provenance)** — the
inference is doing real work in production: 16,454 rows recovered from labels
the crosswalk alone cannot resolve. PII scan of all NDJSON: **0 e-mails, 0 URLs,
0 native refs, 0 PLZ, 0 city strings**. Zero unresolved 4xx; all throttles
absorbed as `throttle_events` (45 s cooldown each). **München (DE212) truncated
at the 400-page cap and was subdivided** into its crosswalk PLZ children with
the segment marked `subdivided`; **zero truncated segments left unsubdivided**.
Structural DoD holds at the session boundary: all Bundesländer complete or
subdivided, all processed Kreise complete or subdivided. The frontier at
`data/state/ba_segment_frontier.json` has **8,171 pending segments** (2,604
complete, 4 subdivided) ready for the next session.

**make check:** 410 tests passed (389 + 21), ruff + mypy strict + pytest green.

**Next session:** run `make scrape-ba-segmented` with `--max-segments 40`
repeatedly (foreground, serial, ~5–15 min per chunk; do NOT pass `--fresh`,
which would discard the frontier) until `make check-ba-segmented` passes. The
remaining ~8,171 segments are the level-2 backbone's tail (Bavaria regions,
the DExx–DEGx states) plus the level-0 unscoped catch-all and level-1
Bundesland probes that come after the backbone; Berlin and Hamburg will each
truncate at 400 pages and subdivide like München. Remaining runtime is on the
order of ~20 h at the measured ~10 chunks/hour; the frontier is durable and a
reap loses at most one segment. Once `make check-ba-segmented` passes, the
`de-stock-segmented` scope is push-ready for the main app (the only main-side
blocker is `_verify_single_scope` — a multi-scope orchestration constraint,
not a data-quality issue).

**SUPERSEDED 2026-08-31 — do not follow the paragraph above.** The census was
cancelled by the descoping decision (see P4 below): do not run
`make scrape-ba-segmented`, do not pass `--fresh`, and never resume the
`de-stock-segmented` scope — a long gap followed by resumption would record a
mass fake `inferred_absence` closure spike downstream. The 8,171 pending
frontier segments will never run; the stored partitions stand untouched.

### 2026-08-31 — P4 (descoping decision: census cancelled, frozen NUTS-3 panel) — no code

**Decision (user, 2026-08-31):** the German census is cancelled. The
observatory's published views need breadth and repeat observations, not
exhaustive counts — a top-25 region table, a per-sweep denominator, and
flow/survival series keyed by scope. A one-shot census cannot populate the
survival views at any size; only repeat sweeps of a frozen panel can.

**Cancelled, not paused:** the ~8,171 pending municipality/PLZ frontier
queries (~20+ h) will never run. A long gap followed by resumption of the same
scope would record a mass fake `inferred_absence` closure spike downstream,
because closures are inferred from any later sweep of the same scope. The 65
stored `de-stock-segmented` partitions (203,674 rows, 99.77% mapped) stand
untouched and that scope is never re-swept.

**New plan for BA Jobsuche (replaces census completion; full detail in
`SCRAPER_ROADMAP.md` Germany step 2b and `SCRAPER_FEASIBILITY.md`):**

1. **Envelope probe FIRST, before building anything:** does the BA response
   envelope carry a total-hits field? If yes, one request per region yields
   exact regional counts and the whole map costs 400 requests. The outcome is
   to be recorded in `SCRAPER_FEASIBILITY.md` (the 2026-08-24 probe found no
   server-rendered `Treffer`/`Ergebnisse` node in the HTML; the envelope /
   embedded SSR state is the open question).
2. **Replace the municipality/PLZ frame with a 400-unit NUTS-3 frame.** The
   destatis Kreise table in the reference crosswalk is the authoritative
   AGS→NUTS 2024 key and covers all 400 GISCO NUTS-3 codes; VZ250 is for
   municipality names only (it carries 7 stale Thuringian codes). Frame sizes
   recorded for traceability: decision text 10,778 units; the lab frontier
   held 10,761 level-2 segments.
3. **Cap-as-scope honesty rule:** the within-stratum page cap must be encoded
   in `scope_json` and stated in `coverage_limitations` ("stratified
   region-bounded sample, not a census"), so `expected_pages ==
   completed_pages` is true of the declared capped scope. A collector that
   caps at k pages and writes k=k without declaring the cap passes every
   downstream test while silently truncating — forbidden (now also in the
   charter's manifest contract).
4. **Frozen panel:** the query set must be byte-identical across sweeps, seed
   recorded. Membership drift between sweeps fabricates closures and corrupts
   survival durations.
5. **Burst:** 400-query region probe, then ~5 daily sweeps of the frozen panel
   (~30 min each, ~3 h total over a week), 1 s pacing per host, zero 4xx.

**Acceptance criteria recorded:** sweep 1 covers ≥390 of 400 NUTS-3 regions;
every sweep `status=complete` with `expected_pages == completed_pages` and
`expected_rows == row_count`; panel membership hash identical across sweeps;
zero failed requests.

**Cuts recorded (roadmap + landscape):** StepStone (~1.5M postings, days of
crawling; cross-source counts are never summed downstream, so a second DE
source adds a non-additive column); Kimeta (grey-ToS HTML, same non-additive
problem); Indeed (stays a charter never-build); other-country re-sweeps
(conditional on the observatory's live-service budget only). BA census
completion: cancelled, not deferred.

**Constraints that still bind (restated, not weakened):** `make check` before
`make sweep`; exactly one source per increment with a Definition-of-Done;
Windows-safe sweep directory names (`YYYYMMDDTHHMMSSZ`); the PII ban (no
names/emails/URLs/postcodes stored); HMAC pseudonymization; robots/ToS
recorded as evidence in feasibility rows (gate relaxed for this private
research project — evidence still mandatory); canary discipline for grey
sources.

**Cadence context:** the observatory may later run as a live service at
weekly cadence (monthly only as a demand snapshot — survival resolution can
never be finer than the sweep interval, and postings live ~30 days). The
panel is designed for weekly re-sweep.

Docs updated: `SCRAPERS.md` (scope decision + cap-as-scope contract rule),
`SCRAPER_ROADMAP.md` (constraints block, census cancelled, step 2b panel plan
with DoD, cuts, risk matrix, parallelization), `SCRAPER_SOURCE_LANDSCAPE.md`
(cut annotations + BA status update), `SCRAPER_FEASIBILITY.md` (Germany
programme table + segmented-stock descope and replacement plan), this log. No
collector code, no sweeps, no stored partitions touched.
