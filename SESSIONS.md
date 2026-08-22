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
