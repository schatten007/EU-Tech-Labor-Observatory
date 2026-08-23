# Scraper Lab — Phased Implementation Plan

Ordered by composite **Feasibility × Volume × Access Certainty**. Quick wins
first to build momentum; Germany (the highest-value market) placed at the
optimal risk/reward point — after two green-light wins, before any grey source.

Cross-cutting foundations (built inside Increment 1, not as separate sources):

- **Collector Interface** — `scrapers/base.py`. Sweden's live JobTech collector
  is the blueprint; the interface standardizes `fetch() -> RawRecord`,
  `normalize() -> SAFE_FIELDS record`, pagination, retry/backoff, and the
  NDJSON + manifest writer so every subsequent source drops into the same
  shape. See `SCRAPERS.md` § Output contract.
- **Compliance helpers** — `scrapers/robots.py` (robots.txt + Crawl-Delay +
  pacing) and `scrapers/sanitize.py` (HMAC pseudonymization + SAFE_FIELDS
  allowlist + PII stripping).
- **Multi-country adapter** — built once in Increment 3 (Adzuna) and reused by
  every country-domain source.

Canary Test (mandatory for grey/HTML sources): a gated pre-deployment step that
fetches a small sample (≤100 records) with 1s+ pacing and randomized
user-agents, verifies robots.txt, confirms zero 4xx/block, and records the
result in `SCRAPER_FEASIBILITY.md` before the full sweep is enabled.

---

## Increment 1: Centralna Baza Ofert Pracy — ePraca (Poland)

- **Priority Score:** **High** — the highest composite (perfect feasibility, L
  volume, sanctioned public access); establishes the Collector Interface on a
  national-scale source.
- **Access Method:** **API** — official SOAP WebService + JSON REST at
  `oferty.praca.gov.pl/integration/services/...`; all active offers as zipped
  JSON batches (1,000/package); no auth for the public search JSON path.
- **Implementation Effort:** **M** — key hurdle is extracting the Collector
  Interface from the JobTech blueprint while keeping Sweden's output byte-identical.
- **Deliverable:** `scrapers/base.py` (Collector Interface + writers),
  `scrapers/robots.py`, `scrapers/sanitize.py`, `scrapers/poland_cbop.py`
  (`CBOPCollector`).
- **Definition of Done:** Collector Interface passes the existing JobTech
  output-contract tests unchanged; CBOP pull of **all active offers** lands
  ≥10,000 observations in `data/raw/collections/cbop/` with `status=complete`,
  zero 4xx, and matching manifest `row_count`.
- **Status:** **DONE 2026-08-21** — see `SCRAPER_FEASIBILITY.md` and
  `SESSIONS.md`. Full sweep: **22,068 observations, 221/221 pages,
  `status=complete`, `expected_rows == row_count == 22,068`, zero 4xx**;
  JobTech output-contract tests pass unchanged (`make check`: 69 tests, mypy
  strict clean).

## Increment 2: Úřad práce / MPSV (Czechia)

- **Priority Score:** **High** — second-highest composite: trivial open-data
  JSON, daily refresh, no auth; another momentum win.
- **Access Method:** **API** — national open-data catalogue
  (`data.gov.cz` / `data.mpsv.cz`), "Volná místa za celou ČR" as JSON /
  JSON-LD / SPARQL; no authentication.
- **Implementation Effort:** **S** — key hurdle is mapping Czech region codes
  to NUTS 2024.
- **Deliverable:** `scrapers/czech_mpsv.py` (`MPSVCollector`).
- **Definition of Done:** Daily pull writes ≥5,000 observations with
  `region_mapping_status` populated; two consecutive daily runs show only new
  postings added and closed postings `removed_at`-stamped.
- **Status:** **DONE 2026-08-22** — see `SCRAPER_FEASIBILITY.md` and
  `SESSIONS.md`. Two consecutive daily sweeps (2026-08-22, 2026-08-23): each
  wrote **38,903 observations, 1/1 pages, `status=complete`,
  `expected_rows == row_count == 38,903`**, zero 4xx; region mapped on
  **98.8%** of records via the MPSV codelist chain (kraj/okres/obec -> NUTS
  2024) with `region_mapping_status` populated on 100% of rows; reconciliation
  `integrity OK` with HMAC-only `closures.ndjson`; ESCO/skill mapping deferred
  (as in Increment 1); `make check` green (113 tests).

## Increment 3: Adzuna (Germany — multi-country adapter)

- **Priority Score:** **High** — the highest-value German entry at the optimal
  point: sanctioned API (no anti-bot, no grey ToS) and L–XL volume, placed
  after two wins so the pattern is proven before the flagship source.
- **Access Method:** **API** — official public REST
  (`api.adzuna.com/v1/api/jobs/{country}/search/{page}`), free `app_id`/`app_key`
  via developer signup; filters incl. keyword, location, salary, contract type.
- **Implementation Effort:** **M** — key hurdle is the **multi-country adapter**
  (18 country domains share one collector; country code + locale + taxonomies
  are config), plus dedupe across Adzuna's source boards.
- **Deliverable:** `scrapers/adzuna.py` (`AdzunaCollector` + `CountryAdapter`),
  reusable for AT/BE/CH/ES/FR/GB/IE/IT/NL/PL and the rest.
- **Definition of Done:** DE sweep pulls **≥100,000 active listings** in
  staging without 4xx; a second country (e.g. NL) runs through the same class
  with only config changes and produces a valid manifest.
- **Status:** **DONE 2026-08-22** — see `SCRAPER_FEASIBILITY.md` and
  `SESSIONS.md`. Live probe pinned the contract: `count` advertises DE
  1,155,948 / NL 190,606 active listings; pages 1..N at 50/page, zero 4xx/429;
  `id` is string on DE / integer on NL; **per-query result window ~100 pages
  (~5,000 unique rows) before the API recycles earlier pages** (probed live).
  Combined with the free tier's documented 250 hits/day, the literal
  "≥100,000 rows in one sweep" is not physically achievable on the free tier —
  stated plainly in the feasibility row and `coverage_limitations` (full DE
  stock would need ~23k segmented hits). DoD evidence: DE sweep
  `de-all-active` 20260822T000000Z **100/100 pages, 4,841 rows,
  `status=complete`, `expected_rows == row_count`, zero 4xx**, unique 64-hex
  HMAC source_ids, zero PII; NL sweep `nl-all-active` 20260823T000000Z
  **100/100 pages, 4,956 rows, `status=complete`, zero 4xx** through the same
  class with config-only change. `make check` green (127 tests).

## Increment 4: France Travail — API Offres d'emploi (France)

- **Priority Score:** **High** — XL volume (9.3M offers/yr), official API; the
  contract onboarding can run in parallel with earlier increments.
- **Access Method:** **API** — official REST; **requires accepting the "Licence
  de réutilisation de la base de données des offres d'emploi"** to obtain
  credentials (free, self-service click-through on francetravail.io — verified
  live 2026-08-22; not a counter-signed bilateral contract as first assumed).
- **Implementation Effort:** **M** — key hurdle is onboarding latency (contract)
  and mapping French ROME/codes to ESCO + NUTS.
- **Deliverable:** `scrapers/france_travail.py` (`FranceTravailCollector`).
- **Definition of Done:** First sweep pulls **≥10,000 active offers** with no
  4xx/401 after credentials land; contract + auth state recorded in
  `SCRAPER_FEASIBILITY.md`.
- **Status:** **DONE 2026-08-22** — see `SCRAPER_FEASIBILITY.md` and
  `SESSIONS.md`. Live probe pinned the contract: OAuth2 client-credentials
  (`expires_in` 1499 s, opaque bearer, 401 + empty body when stale), `range`
  windows answered `206` + `Content-Range: offres a-b/503356`, **hard caps of
  150 items per window and start position ≤ 3000 ⇒ 3,150 offers per query**
  against a **~504k** national active stock, so the sweep segments by
  département (101 codes from a new pinned crosswalk) plus one unsegmented
  query, deduped on HMAC `source_id`; documented and header-confirmed limit
  10 req/s (collector paces at the charter's 1 s floor). **Region is fully
  mapped, not deferred:** the pinned `francetravail_departements_nuts_2024.csv`
  (101 rows, FT `referentiel/departements` × Eurostat GISCO NUTS 2024, 101/101
  bijective name join) resolved **98.1% `mapped`** (commune INSEE), 1.7%
  `low_confidence`, 0.2% `unmapped` across 100 distinct NUTS 3 codes.
  ROME → ESCO deferred as `occupation_mapping_status=unmapped` (the source does
  expose `romeCode`, unlike Increments 1–3). **DoD evidence:** sweep
  `fr-all-active` 20260822T000000Z — **120/120 windows, 17,406 rows,
  `status=complete`, `expected_rows == row_count == NDJSON lines`, zero
  4xx/401**, unique 64-hex HMAC source_ids, zero PII (no e-mail, URL, postcode,
  INSEE code or native id in the output), `first_published`/`last_modified`
  populated on 100% of rows. `make check` green (170 tests).

## Increment 5: VDAB (Belgium — Flanders)

**Re-scoped 2026-08-22 after the feasibility gate.** The original plan (free
`X-IBM-Client-Id` key via self-service app registration → Vacature API v4) is
wrong: VDAB's own documentation requires *"een partnership … en na het
ondertekenen van een samenwerkingsovereenkomst"* (an approved partnership plus a
signed cooperation agreement), professional use only, with a VDAB-side
added-value test. The **API is therefore blocked and is not routed around**. The
implemented surface is instead VDAB's **public job-search website**, which is
robots-permitted and whose disclaimer explicitly allows copying and using the
information for informational purposes. Both verdicts are recorded as two
separate surfaces in `SCRAPER_FEASIBILITY.md`.

- **Priority Score:** **High** — sanctioned public surface, M–L volume; cheap
  regional coverage that Adzuna's BE domain does not fully carry.
- **Access Method:** **HTML** — server-rendered SEO landing pages
  `www.vdab.be/vindeenjob/jobs/<postcode>-<gemeente>` (28 vacancy tiles each,
  with per-segment totals), discovered through the six sitemaps VDAB advertises
  in its own `robots.txt` (34,903 landing pages; 214 weekly vacancy sitemaps
  carrying ids + `lastmod`). **The Angular app's internal JSON API
  (`/api/vindeenjob/`) is robots-DISALLOWED and must not be used** — that is the
  path the public third-party scrapers take, and it is off-limits here.
  ~232,944 active Flanders vacancies advertised on the search page.
- **Implementation Effort:** **S–M** — key hurdles are breadth-based coverage
  (no in-page pagination: `?limit`/`?page`/`?start` are ignored, `/2` 404s, so
  each segment yields its first 28 tiles only) and the postcode → NUTS 3
  crosswalk.
- **Deliverable:** `scrapers/vdab.py` (`VDABCollector`) +
  `scrapers/reference_vdab.py` (pinned postcode → NUTS 2024 crosswalk built from
  Basisregisters Vlaanderen, whose `postinfo/{postcode}` payload returns `nuts3`
  directly — verified live: `9000` → `BE234`).
- **Mandatory Canary Test:** ≤100 records, 1s+ pacing, robots.txt verified, zero
  4xx/block recorded in `SCRAPER_FEASIBILITY.md` before the full sweep.
  **Already PASSED 2026-08-22:** 12 landing pages at 1.2 s → 12/12 HTTP 200,
  zero 4xx, zero challenges, 189 unique ids from 255 tiles, dates and
  contract labels on 100% of tiles. (Deviation on purpose: user-agents are **not**
  randomized — identity-obscuring contradicts the charter, and a single honest
  UA drew zero blocks.)
- **Definition of Done:** pull of Flanders vacancies **≥5,000 records** in
  staging, **zero 4xx**, manifest `expected_pages == completed_pages`, region
  mapped to NUTS 2024 on the bulk of rows, and the gap between rows collected
  and the advertised 232,944 stated plainly in `coverage_limitations`.
- **Status:** **DONE 2026-08-22** — see `SCRAPER_FEASIBILITY.md` and
  `SESSIONS.md`. Contract re-verified live before the build (robots.txt
  unchanged at 3,564 bytes with `/api/vindeenjob/` still disallowed; the
  no-pagination contract re-probed: `?limit`/`?page`/`?start` returned the
  identical 28 ids and `/2` answered 404). Region is **fully mapped, not
  deferred:** the pinned `vdab_postcode_nuts_2024.csv` (**528 rows**, 529
  postcodes enumerated from Basisregisters Vlaanderen × Eurostat GISCO NUTS
  2024, **0 unmatched**, all **22 Flemish NUTS 3** codes present) resolves the
  landing-page slug's postcode. Coverage is breadth-based by design: landing
  pages are breadth-ordered so one page per distinct Flemish postcode comes
  first, which is why 500 pages dropped only 5 duplicates. **DoD evidence:**
  sweep `be-flanders-all-active` 20260822T000000Z — **500/500 landing pages,
  12,282 rows** (12,287 tiles, 5 duplicates dropped on HMAC `source_id`),
  `status=complete`, `expected_pages == completed_pages`,
  `expected_rows == row_count == NDJSON lines`, **zero 4xx**, unique 64-hex HMAC
  source_ids, region **`mapped` 100%** across all **22 Flemish NUTS 3
  arrondissements**, `first_published` on 100% of rows, zero PII (0 e-mails,
  0 URLs, 0 postcodes, 0 native ids). Honest gap in `coverage_limitations`:
  **12,282 of the advertised 232,944** (5.3%) — 28 tiles per page with no
  pagination. `make check` green (215 tests).

## Increment 6: NAV stillings-feed (Norway)

- **Priority Score:** **Medium-High** — L volume and ~1,000 new/day, but JWT
  consumer registration and continuous-feed semantics add run complexity.
- **Access Method:** **Feed** — official JSON feed API
  (`pam-stilling-feed.nav.no/api/v1/feed`), JWT bearer auth (consumer
  registration; public experimentation token available), `next_url` pagination,
  `If-Modified-Since`/`ETag`.
- **Implementation Effort:** **M** — key hurdle is ACTIVE/INACTIVE
  reconciliation (the feed is append-only events, not a snapshot).
- **Deliverable:** `scrapers/nav_norway.py` (`NAVFeedCollector`).
- **Definition of Done:** Initial backfill + a daily poll cycle produce ≥5,000
  records with `removed_at` correctly stamped on INACTIVE ads; token rotation
  handled without downtime.
- **Status:** **DONE 2026-08-23** — see `SCRAPER_FEASIBILITY.md` and
  `SESSIONS.md`. Contract re-verified live before the build and it **corrected
  NAV's own documentation twice**: revalidation needs `If-None-Match` **alone**
  (adding `If-Modified-Since` re-seeks and answers 200; `If-None-Match` alone
  answers **304 with a 0-byte body**), and the migration pseudocode's
  `_feed_entry.id` does not exist — the field is `uuid`. robots.txt is **absent**
  (404) so nothing is disallowed, and unauthenticated requests answer 401 with no
  `WWW-Authenticate`, so the keyed-API reading from Increments 3–4 applies. The
  ToS (`arbeidsplassen.nav.no/vilkar-api`) names *"statistiske/analytiske
  formål"* as an **independent permitted purpose**, so this is allowed outright;
  the public experimentation token is used and **no private-token request has
  been sent** (recorded as not started). This increment is the lab's first
  **event-log** source (folded per ad uuid on the HMAC `source_id`, ~2.0 events
  per ad), its first **source-reported `removed_at`** (so no MPSV-style
  reconciliation pass is needed), and its first **native ESCO occupation URI**
  (`ad_content.categoryList`), with `esco_occupation_label` left `None` on
  purpose because the source's label is Norwegian and this project publishes
  English. **Region is fully mapped:** the pinned `nav_region_nuts_2024.csv`
  (**370 rows** — 15 fylke + 353 kommune + 2 deliberately `ambiguous` repeated
  names; SSB Klass 104/131 × Eurostat GISCO NUTS 2024, **15/15 fylker joined, 0
  unmatched**) resolves **98.2%** of rows to a NUTS 3 code across **all 15
  mainland Norwegian NUTS 3 regions**. **DoD evidence:** backfill
  `no-all-events` 20260822T000000Z — **20/20 pages, 20,000 events → 10,342
  rows**, `status=complete`, `expected_rows == row_count == NDJSON lines`, zero
  4xx, **5,134/5,134 INACTIVE rows `removed_at`-stamped**, 1,172 ESCO URIs
  (81.7% of the 1,434 detail-enriched rows); poll cycle 20260823T000000Z —
  **resumed from the persisted cursor**, 6/6 pages, 4,600 events → **2,239
  rows**, reconciled, zero 4xx, reached the true end of feed (`next_url`/
  `next_id` null) and reused the cached token (0 token requests). **Token
  rotation proven live:** the overnight-rotated cached token produced a 401 on
  the backfill's first authorized request, which the collector refreshed once and
  replayed with no lost page (`token_refreshes=1`). Combined **12,581 rows over
  12,051 distinct ads**, PII scan clean. Honest bound in `coverage_limitations`:
  a sweep is a **window over an event log**, not a snapshot — bounded by
  `--since`, by the `--max-details` budget (1 paced request per enriched row) and
  by Finn.no's documented absence, with no advertised active-stock total to
  compare against. A **NAV-side reliability incident** (26–28 s token responses,
  500/504, read timeouts) was met with back-off plus three hardenings (90 s
  timeout, cached public token, 5xx-tolerant detail fetches). `make check` green
  (313 tests).

## Increment 7: Työmarkkinatori / Job Market Finland (Finland)

- **Priority Score:** **Medium** — ESCO-native structured data is high quality,
  but onboarding (KEHA activation form) and M volume temper the score.
- **Access Method:** **API** — official REST + **NDJSON streaming** (P67 via
  Kipa); requires terms acceptance + activation form → API key.
- **Implementation Effort:** **M** — key hurdle is the onboarding/credentials
  process and consuming the NDJSON stream shape.
- **Deliverable:** `scrapers/finland_tmt.py` (`FinlandTMTCollector`).
- **Definition of Done:** Streamed pull of active postings ≥5,000 records with
  ESCO occupation/skill URIs populated; no 4xx/401 after credentials issued.
- **Status:** **BLOCKED 2026-08-23 — collector built, DoD pending KEHA
  activation.** See `SCRAPER_FEASIBILITY.md` and `SESSIONS.md`. The contract was
  pinned live from the **published OpenAPI description**
  (`P67-tmt-provider-haku-V2`, 19,115 bytes) plus the technical documentation,
  and it corrected two roadmap assumptions. First, the interface is **not merely
  form-gated**: KEHA issues the `KIPA-Subscription-Key` *and* opens the caller's
  IP address, and both Kipa hosts (`api.ahtp.fi`, `api-qa.ahtp.fi`) **drop TCP
  443 from a non-allowlisted address** (21 s timeouts) while a sibling
  `ahtp.fi` host answers in 0.52 s — so **there is no public sandbox** and the
  QA environment is credential-gated too. Second, the API has **no pagination,
  no cursor and no terminal sentinel**: `FiltersV2` carries only `onlyStatus`
  plus five `{from, to}` intervals and eight set filters, so **one POST streams
  one whole result set** and the "cursor" is a client-side watermark (max
  `metadata.lastModified`, persisted to `data/state/finland_tmt_cursor.json`).
  **A third finding changed the build:** the portal's own codeset service, which
  the technical documentation points at for `KUNTA`/`MAAKUNTA`/`ESCO_AMMATTI`,
  sits under `tyomarkkinatori.fi/api/`, which `robots.txt` **disallows**
  (`Disallow: /api/`, `Disallow: /*/api/`) — so it is not touched (the VDAB
  `/api/vindeenjob/` precedent) and the crosswalk is built from **Statistics
  Finland** instead. **Region is fully mapped:** the pinned
  `finland_tmt_region_nuts_2024.csv` (**327 rows** — 308 kunta + 19 maakunta + 0
  ambiguous; Statistics Finland `kunta_1_20260101#nuts_2_20260101`, which names
  itself *"virallinen NUTS 2024"*, × Eurostat GISCO NUTS 2024, **all 19 Finnish
  NUTS 3 codes present, 0 unmatched, 0 GISCO codes without a municipality**), and
  the maakunta layer is **derived then verified** single-valued, proving
  empirically that a Finnish maakunta *is* a NUTS 3 region. This is also the
  lab's **first source to populate `skill_mappings`** and its second with a
  **source-reported `removed_at`** (`metadata.archived`). Occupation and skills
  come from the source's own **FINESCO 1.2.0-R8** distribution, whose universe is
  measurably not pure ESCO (3,046 ESCO occupations, 619 ISCO groups, **78 Finnish
  national extensions**; 15,163 ESCO skills + 220 ISCED-F), so values are
  classified into five honest outcomes rather than coerced. **Honest blocker:**
  the activation notification was **deliberately not submitted** — it is an
  organisation-level commitment bound to a Finnish **Y-tunnus** with a KEHA
  suitability check, which this lab cannot truthfully satisfy — so **no key is
  held and 0 postings were retrieved**. The DoD sweep waits for the key; the
  increment is **not** claimed as DONE. `make check` green (**367 tests**).

## Germany — ACTIVE LANE (user reorder 2026-08-23)

Germany is the highest-value market and the least covered (Adzuna DE 4,841 of
~1.16M advertised = 0.4%), so it becomes the active lane. The constraint is
**ToS/robots.txt relaxed for this private educational project** (the user's
explicit decision); the real gates are now **technical accessibility** (anti-bot
systems, WAFs) and **litigation risk** (Indeed). The serial rule for grey-HTML
sources is dropped — the German sources are built in technical-feasibility order,
not serially. Increment 7 (Finland) stays parked-BLOCKED.

**German coverage stack — every surface assessed technically live 2026-08-23:**

| # | Source | Volume | Technical access (verified) | Role |
| --- | --- | --- | --- | --- |
| 1 | **BA Jobsuche** (public website) | ~1.9M | **SSR, plain HTTP, no anti-bot.** `www.arbeitsagentur.de/jobsuche/suche?was=...&wo=...` → 200, 370 KB, server-rendered HTML with job titles, employer, publish date, location+distance, salary, employment type, homeoffice, native ref IDs (`Stellenangebot 10000-1202838080-S`). robots.txt absent (404) on the search host. | **PRIMARY BUILD — the single biggest German prize** |
| 2 | **StepStone.de** | ~1.5M+ | **SSR, plain HTTP, JSON-LD on detail pages.** `www.stepstone.de/jobs/...` → 200, 1.1 MB, `application/ld+json` present. Akamai Bot Manager not visible on search pages. | **SECONDARY BUILD** |
| 3 | **Indeed.de** | ~1.5M+ | **SSR, plain HTTP, data-jk ids.** `de.indeed.com/Jobs?q=...` → 200, 1.3 MB, `data-jk="..."` for HMAC. **Litigation risk** — Indeed has sued scrapers. | **TERTIARY — gate evaluates risk** |
| 4 | **Kimeta.de** | ~1.5–1.8M | **No anti-bot technical barrier.** robots.txt `*`→`Disallow:/` is the only barrier (relaxed). Homepage 200, 214 KB; search API at `/api/mutation/create-jobalert-and-search`; content pages at `/stellenangebote`, `/stellenmarkt`. | **FOURTH BUILD** |
| 5 | **Stellenanzeigen.de** | ~10k+ | **robots-permitted, JSON-LD, Cloudflare passive.** `/job/*` and `/suche/*` ALLOW, three sitemaps. | **FIFTH BUILD** (smaller volume) |
| 6 | **Joblift.de** | L (per-city 20-27k) | **CloudFront 403 at the edge** — robots.txt AND `/business-developer` (partner API) both 403'd. May be UA-blockable. | **SIXTH — needs real-browser test** |
| 7 | **Monster.de** | L | **DataDome challenge** — robots.txt 403 with JS challenge (`geo.captcha-delivery.com`). Requires browser automation + proxy. | **SEVENTH — requires tooling decision** |
| 8 | **Interamt.de** | ~90k/yr public | **Redirect loop for curl, JS-only.** Playwright-dependent. | **EIGHTH — gate only** |
| — | **Adzuna DE (Inc 3)** | ~1.16M | Sanctioned API, free key, **DONE** (4,841 rows/sweep free-tier cap). | **Sanctioned base — keep daily** |
| — | **Arbeitnow (Inc 11)** | ≤5k tech | Keyless official API, clean, **trivial build**. | Cheap fill (interleave) |
| — | **EURES DE slice (Inc 12)** | ~1.8M EU | Arrangement-gated, ESCO-native. | Access track (parallel) |

**Technical notes on the top three:**
- **BA Jobsuche** is SSR on the `www.arbeitsagentur.de` origin. Its internal REST API
  (`rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs`) is **WAF-gated**
  even from the same browser context (403) — the SSR page works, the direct API does
  not. The collector is an HTML parser, not an API client. Pagination is through the
  SPA's server-rendered search pages (`&page=N`). The search results page carries
  native posting refs for HMAC pseudonymization.
- **StepStone** returns 200 with content (~1.1 MB) for search pages. The Akamai Bot
  Manager documented in the roadmap may be passive on search pages or active on
  detail pages. The canary must probe both.
- **Indeed** returns 200 with content (~1.3 MB) for search pages. The litigation risk
  is real and documented: Indeed (Recruit Holdings) has a history of suing scrapers.
  This is flagged in the feasibility row, not hidden.

**New prerequisite — the German region crosswalk (not previously scheduled):**
every German source needs location → NUTS 3 2024. Germany has **400 NUTS 3 codes**
(Eurostat GISCO `NUTS_AT_2024.csv`, verified). Authority: **BKG Geodatenzentrum**
(`gdz.bkg.bund.de`, only GPTBot blocked) Orts-/Gemeindeverzeichnis (PLZ + AGS),
cross-checked with **destatis.de** (allow, `Crawl-delay: 30`), validated against
GISCO. Deliverable `scrapers/reference_germany.py` + pinned
`germany_plz_nuts_2024.csv`, 0-unmatched bar, built before any HTML collector.

**Access tracks running in parallel (no scraper, no code):** the BA Jobsuche
agreement (HR-BA-XML) and the EURES arrangement. These are the structured-data
routes; the HTML surface is the main path regardless.

**Cross-source overlap stance:** aggregators share boards. Cross-source dedupe is
**not possible at collection** — SAFE_FIELDS carries no join key. Overlap is
accepted and stated per source in `coverage_limitations`.

**Germany execution order (next sessions):**
1. `reference_germany.py` (BKG × GISCO, 400 codes, 0 unmatched) — needed by every
   German collector.
2. **BA Jobsuche** feasibility gate (probe the detail page, pagination, extract the
   native ref ID pattern, location fields) → `BAJobsucheCollector` → canary → DoD
   sweep.
3. **StepStone** feasibility gate → `StepStoneCollector` → canary → DoD sweep.
4. **Indeed** gate evaluates litigation risk → build or flag.
5. Subsequent sources in technical-feasibility order.
6. Arbeitnow (keyless API, interleave).
7. BA agreement + EURES arrangement status updates.

**Foolproof mechanisms:** mandatory technical-feasibility gate before every build
(probe the actual pages, not just robots; verify no anti-bot challenge; measure
page size, speed, structure), canary (≤100 records, 1 s+ pacing), mini-canary
before the full sweep, manifest reconciliation, PII scan, NAV-style incident
hardening, honest coverage bound in every manifest. The ToS/robots gate is
explicitly **relaxed** for this project; it is still recorded as evidence in the
feasibility row but does not block a build.

## Increment 8: Kimeta.de (Germany — largest aggregator)

- **Priority Score:** **Medium** — XL volume (~1.5–1.8M) is the highest German
  count, but **ToS grey** + HTML scraping push it to the middle; placed only
  after the sanctioned German path (Adzuna) is proven.
- **Access Method:** **HTML** — no public API; search-engine HTML with
  filters, per-city/keyword pages; third-party scrapers exist as reference.
- **Implementation Effort:** **L** — key hurdles are pagination + dedupe across
  75+ regional feeds and live robots/ToS verification.
- **Deliverable:** `scrapers/kimeta.py` (`KimetaCollector`).
- **Mandatory Canary Test:** ≤100 records, 1s+ pacing, randomized user-agents,
  robots.txt verified, zero 4xx/block recorded in `SCRAPER_FEASIBILITY.md`
  before the full sweep.
- **Definition of Done:** Full sweep pulls **≥100,000 unique listings** in
  staging with zero 4xx and successful canary evidence.

## Increment 9: Joblift (Germany + FR/UK/NL/BE)

- **Priority Score:** **Medium-Low** — L volume across 5 EU markets but **HTML**
  scraping + grey ToS; same risk profile as Kimeta at lower volume.
- **Access Method:** **HTML** — no public read API; per-market domains
  (joblift.de/.fr/.co.uk/.nl/.be).
- **Implementation Effort:** **M** — key hurdle is multi-domain HTML parsing +
  dedupe and live ToS verification.
- **Deliverable:** `scrapers/joblift.py` (`JobliftCollector`).
- **Mandatory Canary Test:** ≤100 records per domain, 1s+ pacing, randomized
  user-agents, robots.txt verified, zero 4xx/block before the full sweep.
- **Definition of Done:** DE sweep ≥10,000 records; at least one secondary
  market (NL or BE) also pulls cleanly with canary evidence recorded.

## Increment 10: Stellenanzeigen.de (Germany)

- **Priority Score:** **Low-Medium** — M volume but grey ToS + Cloudflare; only
  worth doing after Adzuna/Kimeta, and only if German coverage still has gaps.
- **Access Method:** **HTML + JSON-LD** — server-rendered detail pages carry
  `JobPosting` JSON-LD; Cloudflare protection reported; TLS-fingerprinting HTTP
  client (no browser) required.
- **Implementation Effort:** **M** — key hurdle is Cloudflare handling and
  promoted-listing ordering.
- **Deliverable:** `scrapers/stellenanzeigen.py` (`StellenAnzeigenCollector`).
- **Mandatory Canary Test:** ≤100 records, 1s+ pacing, randomized user-agents,
  robots.txt verified, zero 4xx/block before the full sweep.
- **Definition of Done:** Pull of active listings ≥5,000 records with zero 4xx
  and canary evidence recorded.

## Increment 11: Arbeitnow (Germany/UK — tech niche)

- **Priority Score:** **Low-Medium** — trivial keyless API and clean ToS, but
  **S–M volume confined to tech/remote/startups**; a spare quick win to slot in
  if the Germany tech slice needs breadth.
- **Access Method:** **API** — official keyless JSON
  (`arbeitnow.com/api/job-board-api`, documented via Postman); UK twin at
  arbeitnow.co.uk.
- **Implementation Effort:** **S** — key hurdle is none (smallest integration in
  the plan).
- **Deliverable:** `scrapers/arbeitnow.py` (`ArbeitnowCollector`).
- **Definition of Done:** Pull of all listings (≤5k) with zero 4xx; `remote` +
  `visa_sponsorship` fields mapped into `skill_mappings`/`number_of_vacancies`.

## Increment 12: EURES portal API (EU-wide)

- **Priority Score:** **Medium-Low** — XL volume (~1.8M) but the API is
  **reverse-engineered** (grey ToS) and ESCO-native data quality varies by
  feeding PES; the crown of the EU-wide view, deferred until a data-access
  arrangement is clarified.
- **Access Method:** **API** — JSON REST at
  `europa.eu/eures/api/jv-searchengine/...` (community-documented OpenAPI),
  self-assigned `sessionId`, country/occupation/skill filters.
- **Implementation Effort:** **M** — key hurdle is the undocumented contract +
  legal arrangement, not the code.
- **Deliverable:** `scrapers/eures.py` (`EURESCollector`).
- **Definition of Done:** Filtered per-country pulls ≥10,000 records with ESCO
  URIs populated; arrangement status recorded before a full EU sweep is run.

## Increment 13: Latvijas Nodarbinātības Valsts Aģentūra (Latvia)

- **Priority Score:** **Low** — open-data daily refresh (allowed) but S–M
  volume; cheap breadth, low risk.
- **Access Method:** **API** — open-data portal `data.gov.lv`, "Vakances"
  dataset with API access, daily refresh.
- **Implementation Effort:** **S** — key hurdle is NUTS mapping for LV regions.
- **Deliverable:** `scrapers/latvia_nva.py` (`NVACollector`).
- **Definition of Done:** Daily pull ≥1,000 records with `country=LV` and zero
  4xx.

---

## Not planned (excluded by the feasibility gate)

| Source | Reason |
| --- | --- |
| BA Jobsuche | ToS-prohibited; only implementable via a BA/HR-BA-XML data agreement (an access-request increment, not a scraper) |
| Meinestadt.de | ToS-prohibited + Akamai Bot Manager |
| StepStone | ToS-prohibited + Akamai Bot Manager |
| Indeed | ToS-prohibited + Cloudflare + litigation history |
| Jobnet (DK) | Restricted B2B agreement only |
| VDAB Vacature API v4 | Requires a VDAB-approved partnership + signed *samenwerkingsovereenkomst* (verified 2026-08-22). Only implementable as an access-request task, not a scraper. **The public vdab.be job-search site remains in scope as Increment 5** (robots-permitted, disclaimer allows informational re-use). |

---

## Risk Matrix

| Increment | Source | Legal risk | Technical risk | Data-quality risk | Overall |
| --- | --- | --- | --- | --- | --- |
| 1 | CBOP PL | Low (public) | Low | Med (PES subset, 174 fields noisy) | **Low** |
| 2 | MPSV CZ | Low (open data) | Low | Low (official daily feed) | **Low** |
| 3 | Adzuna DE | Low (API ToS) | Med (rate limits, board dedupe) | Med (aggregator quality) | **Low-Med** |
| 4 | France Travail | Low (contract) | Med (onboarding latency) | Low (official) | **Low-Med** |
| 5 | VDAB BE (public site) | Low-Med (robots-permitted HTML; API surface blocked and dropped) | Med (no in-page pagination, breadth-based coverage) | Med (Flanders only, no occupation code) | **Low-Med** |
| 6 | NAV NO | Low (agreement) | Med (feed reconciliation) | Low-Med (Finn.no excluded) | **Med** |
| 7 | Finland TMT | Low-Med (activation bound to a Finnish Y-tunnus; KEHA suitability check) | Med (NDJSON stream, credentials **+ IP allowlist**) | Low (ESCO-native) | **Med (parked-BLOCKED)** |
| 8 | Kimeta DE | **Low** (relaxed: no ToS/robots barrier for this project; no anti-bot) | **Med** (JS-driven HTML, pagination across 75+ feeds) | Med (aggregator) | **Low-Med** |
| 9 | Joblift | **Med** (relaxed: no ToS/robots barrier; CloudFront 403 is a technical anti-bot question) | **High** (CloudFront edge block — needs browser test) | Med | **High (gate pending)** |
| 10 | Stellenanzeigen DE | **Low** (relaxed: no ToS/robots barrier; robots already permitted) | **Med** (JSON-LD HTML, passive Cloudflare) | Low-Med (JSON-LD) | **Low-Med** |
| 11 | Arbeitnow | Low (public API) | Low | **High** (tech-only niche) | **Low-Med** |
| 12 | EURES | **High** (grey, undocumented) | Med | Med (varies by PES) | **High** |
| 13 | Latvia NVA | Low (open data) | Low | Med (S volume) | **Low** |

Mitigation for all High-risk rows: mandatory Canary Test + per-target
`SCRAPER_FEASIBILITY.md` row before any full sweep, per the charter's
feasibility gate.

## Parallelization Recommendation

- **Increment 1 → 2 → 3 are strictly sequential.** The Collector Interface
  (Inc 1) must exist before any other source; 2 and 3 then validate it. This
  chain is the lab's backbone.
- **Increment 4 (France Travail)** can **start onboarding (contract) in
  parallel with Increments 1–3**; only the credential-dependent build work
  waits.
- **Increments 6 (NAV) and 7 (Finland)** can be built in parallel with 4–5
  once the interface is stable (Inc 1 done) — they use different transports
  (feed, NDJSON) and their registration processes run independently. **Increment 7
  is now parked-BLOCKED** (build complete, DoD pending KEHA activation — the
  activation notification is bound to a Finnish Y-tunnus this lab does not hold).
- **Germany is the active lane.** The user re-ordered the roadmap to make Germany
  the active build target **and relaxed the ToS/robots gate for this private
  educational project** — the remaining gates are technical (anti-bot) and
  litigation risk. The 2026-08-23 live probes put **BA Jobsuche's public website
  first** (~1.9M, SSR, no anti-bot, plain HTTP), then **StepStone** (~1.5M+,
  SSR, JSON-LD), **Indeed** (~1.5M+, SSR, litigation-flagged), **Kimeta**
  (~1.5–1.8M, no anti-bot, JS-driven), **Stellenanzeigen** (~10k+, robots-
  permitted, JSON-LD), then Joblift/Monster/Interamt behind technical barriers.
  The German region crosswalk (``reference_germany.py``, BKG × GISCO, 400 NUTS 3
  codes) is a **new prerequisite** built before the first HTML collector. The BA
  HR-BA-XML agreement and the EURES arrangement run in parallel as structured-
  data access tracks.
- **The German HTML chain is ordered by technical feasibility, not serial-only:**
  each source gets its own technical-feasibility gate and canary (≤100 records,
  1 s+ pacing, anti-bot probe), and canaries for independent hosts **may run
  concurrently** — the serial rule that mattered was for overlapping crawls of
  the *same* host under the old constraint. Increment 5 (VDAB) stays in the
  HTML-canary class; its canary already passed (2026-08-22).
- **Increments 11 (Arbeitnow) and 13 (Latvia NVA) are fillers** — slot into any
  idle cycle; they share no moving parts with the critical path.
- **Recommended team shape:** one lane on the German active lane (region
  crosswalk → BA Jobsuche → StepStone → Indeed-gate → Kimeta), one lane on
  access tracks (BA HR-BA-XML agreement, EURES), one lane on the interleave
  fillers (Arbeitnow, Adzuna country expansion). Data writes are the only shared
  resource and are per-source-partition isolated on disk, so lanes do not
  contend.
