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

- **Priority Score:** **High** — Low/Low complexity, sanctioned open data, M
  volume; cheap regional coverage that Adzuna's BE domain does not fully carry.
- **Access Method:** **API** — official open-data portal
  (`developer.vdab.be/opendata`), free API key via app registration
  (`X-IBM-Client-Id` header), Vacature API v4.
- **Implementation Effort:** **S** — key hurdle is Flemish-only coverage
  (Wallonia `Le Forem` / Brussels `Actiris` are separate, out of scope here).
- **Deliverable:** `scrapers/vdab.py` (`VDABCollector`).
- **Definition of Done:** Pull of Flanders vacancies ≥5,000 records in staging,
  zero 4xx, manifest `expected_pages == completed_pages`.

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

---

## Risk Matrix

| Increment | Source | Legal risk | Technical risk | Data-quality risk | Overall |
| --- | --- | --- | --- | --- | --- |
| 1 | CBOP PL | Low (public) | Low | Med (PES subset, 174 fields noisy) | **Low** |
| 2 | MPSV CZ | Low (open data) | Low | Low (official daily feed) | **Low** |
| 3 | Adzuna DE | Low (API ToS) | Med (rate limits, board dedupe) | Med (aggregator quality) | **Low-Med** |
| 4 | France Travail | Low (contract) | Med (onboarding latency) | Low (official) | **Low-Med** |
| 5 | VDAB BE | Low (open data) | Low | Med (Flanders only) | **Low** |
| 6 | NAV NO | Low (agreement) | Med (feed reconciliation) | Low-Med (Finn.no excluded) | **Med** |
| 7 | Finland TMT | Low (agreement) | Med (NDJSON, credentials) | Low (ESCO-native) | **Low-Med** |
| 8 | Kimeta DE | **High** (grey) | **High** (HTML, dedupe) | Med (aggregator) | **High** |
| 9 | Joblift | **High** (grey) | **High** (multi-domain HTML) | Med | **High** |
| 10 | Stellenanzeigen DE | **High** (grey) | **High** (Cloudflare) | Low-Med (JSON-LD) | **High** |
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
  (feed, NDJSON) and their registration processes run independently.
- **Increments 8–10 (Kimeta / Joblift / Stellenanzeigen)** must **not**
  overlap each other: each is a grey/HTML source requiring its own Canary Test
  and canary result recording before full deployment. Run serially, spaced by
  at least one clean-sweep session each.
- **Increments 11–13 are fillers** — slot into any idle cycle; they share no
  moving parts with the critical path.
- **Recommended team shape:** one lane on the sequential backbone (1→2→3),
  one lane on agreement/credential sources (4, 6, 7), one lane on the
  grey-HTML canary chain (8→9→10). Data writes are the only shared resource
  and are per-source-partition isolated on disk, so lanes do not contend.
