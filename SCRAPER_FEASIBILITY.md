# Scraper Feasibility Records

Per-target feasibility checklist for the scrapers lab. A target is implemented
only after its checklist row is complete and shows: permissive `robots.txt`,
Terms of Service that do not prohibit automated read access, and the fields
needed for the SAFE_FIELDS contract.

## Context

This replaces `SOURCE_FEASIBILITY.md`. The decisions recorded there (approving
only JobTech, rejecting all German sources) were correct for the main
observatory project, whose scope was a single approved Sweden keyword sweep.
This lab has a different scope: **ethical crawlers for easy-to-scrape public job
boards**. Nothing in the old file binds this worktree, and those decisions are
not carried forward.

## Checklist template

For each candidate, fill in the fields below and record the decision.

```
### [Source name]

| Item | Status | Notes |
| --- | --- | --- |
| **URL** | | |
| **robots.txt fetched** | yes / no | |
| **robots.txt disallowed paths** | | List paths that are off-limits; note any |
| **Crawl-Delay** | N / X s | |
| **ToS reviewed** | yes / no | |
| **ToS automated-access clause** | allowed / restricted / prohibited | Quote or link the relevant clause |
| **SAFE_FIELDS coverage** | complete / partial / missing | Which fields are available? |
| **PII risk** | none / low / high | Any personal data in listings? |
| **Rate limits** | documented / unknown / none | |
| **Snapshot semantics** | full sweep / paginated / no | |
| **Licence / attribution** | | |
| **Decision** | implement / blocked / rejected | Date and reason |
```

## Candidates

### CBOP / ePraca (Poland) — Increment 1

| Item | Status | Notes |
| --- | --- | --- |
| **URL** | | API: `https://oferty.praca.gov.pl/portal-api/v3/oferta/wyszukiwanie` (POST, body `{"kodJezyka":"PL"}`, no auth). Integrator SOAP service (`/integration/services/v2/oferta`) exists but requires a ministry-registered Partner (verified live: `Niepoprawna autoryzacja`), so the sanctioned public search JSON path is used. |
| **robots.txt fetched** | yes | `https://oferty.praca.gov.pl/robots.txt` returns **404 — absent**. No disallowances, no Crawl-Delay. |
| **robots.txt disallowed paths** | none | Nothing disallowed (no robots file). The 1s+ per-host pacing floor from the charter applies regardless. |
| **Crawl-Delay** | none | No directive; charter floor of 1s used. |
| **ToS reviewed** | yes | Portal footer: content licensed **Creative Commons BY 3.0 PL** and "Krajowe i zagraniczne oferty pracy ... mogą być pobierane ze strony ePraca w celu prezentacji na innych portalach lub stronach internetowych na warunkach określonych w sekcji «Dla integratorów»". The ministry publishes an official integrator manual (`instrukcja-pobierania-ofert-pracy-z-systemu-ePraca.pdf`) documenting external download. |
| **ToS automated-access clause** | allowed | External downloads are the documented integrator use case; CC BY 3.0 PL re-use licence. |
| **SAFE_FIELDS coverage** | partial | Available: `source`, `source_id` (HMAC of `id`), `scope_id`, `sweep_id`, `observed_at`, `first_published` (`dataDodaniaCbop`), `removed_at` (status != "A"), `country=PL`, `number_of_vacancies` (default 1; list payload exposes no per-offer total), `nuts_*` mapping deferred (Increment 2-style crosswalk). ESCO/skill mappings deferred to enrichment. |
| **PII risk** | high | Offers carry employer name, contact person, phone, email, addresses — none are allowed into the SAFE_FIELDS output (`extra="forbid"` on `NormalizedRecord` enforces this). |
| **Rate limits** | undocumented | No documented limit on the public search JSON path; the SPA itself pages through it. 1s+ pacing + Retry-After handling implemented. |
| **Snapshot semantics** | paginated | Spring Data `Page` (`totalElements`, `totalPages`, `last`, `content`); full sweep = pages 0..totalPages-1. Verified live: 22,066 proposals, 221 pages at size 100. |
| **Licence / attribution** | | CC BY 3.0 PL: `https://creativecommons.org/licenses/by/3.0/pl/` |
| **Decision** | implement | 2026-08-21. Live probes status 200, zero 4xx. Canary (1 page): 100 rows, zero 4xx, SAFE_FIELDS clean. **Full DoD sweep:** 22,068 observations, 221/221 pages, `status=complete`, `expected_rows == row_count`, zero 4xx. |

### Úřad práce / MPSV — "Volná místa za celou ČR" (Czechia) — Increment 2

| Item | Status | Notes |
| --- | --- | --- |
| **URL** | | Full active-set dump: `https://data.mpsv.cz/od/soubory/volna-mista/volna-mista.json` (single JSON object `{"polozky": [...]}`, no pagination, ~186 MB, 38,903 records at 2026-08-21 probe). Schema: `.../volna-mista.schema.json` (draft-04). Region codelists: `.../ciselniky/kraje.json` (14 entries, carries `kodNuts3` = CZ010–CZ080), `okresy.json` (78), `obce.json` (6,258). "Přírůstky" (daily-increment) dataset exists in NKOD but publishes no file distribution (schema only; its SPARQL endpoint on data.gov.cz is robots-disallowed) — not needed, the full dump suffices. |
| **robots.txt fetched** | yes | `https://data.mpsv.cz/robots.txt` → `User-Agent: * / Disallow:` — everything allowed, no Crawl-Delay. `https://data.gov.cz/robots.txt` → disallows `/sparql*`, `/fct/`, `/describe/`, `/zdroj/` (not relevant to the dump host; rules out the NKOD SPARQL path). |
| **robots.txt disallowed paths** | none (data.mpsv.cz) | Nothing disallowed on the data host. Charter floor of 1 s per request applies; the daily sweep is a single request. |
| **Crawl-Delay** | none | No directive; charter 1 s floor used. |
| **ToS reviewed** | yes | MPSV "Podmínky užití" (`https://data.mpsv.cz/web/data/podminky-uziti`, updated 2022-05-04): standard NKOD open-data declarations for all distributions — no copyrighted works, not a database-protected work, no *sui generis* database right, no personal data in the distribution. Catalogue content on data.gov.cz is **CC BY 4.0**. Legal basis: zákon č. 435/2004 Sb. (o zaměstnanosti, § 35/37). Dataset page documents the export filters (only vacancies with `pocetMist>0`, approved, within the publication window). |
| **ToS automated-access clause** | allowed | National open-data catalogue with daily refresh is published explicitly for download/consumption; no automated-access restriction found. |
| **SAFE_FIELDS coverage** | partial (complete for this scope) | `source=mpsv`, `source_id` (HMAC of `portalId`), `first_published` (`datumVlozeni`, 100%), `last_modified` (`datumZmeny`, 100%), `number_of_vacancies` (`pocetMist`, 100%), `country=CZ`, `lang=cs`, region via codelist chain (workplace kraj 90.7% → contact address `low_confidence` → okres → obec; statuses mapped/ambiguous/low_confidence/unmapped). `removed_at` derived by cross-sweep reconciliation (`expirace` source-reported when present, else next-sweep `observed_at`). ESCO occupation/skill mapping deferred (occupation_mapping_status=`not_present`), as in Increment 1. |
| **PII risk** | high | Raw dump contains contact-person names, emails, telephones, street addresses/PSC (`prvniKontaktSeZamestnavatelem`, `pracoviste[]`, `zamestnavatel` incl. personal names). **None allowed into output** — allowlist-only parse + `NormalizedRecord(extra="forbid")`; PII-isolation test required. Source itself omits employer/workplace info for anonymous postings (`ZverejnovatVpm/anosp`). |
| **Rate limits** | none documented | No documented limit; one full-dump GET per day plus reference-build codelist GETs. Backoff/Retry-After via `scrapers/retry.py` regardless. |
| **Snapshot semantics** | full sweep | Single full-dump JSON per day (no pagination, no cursor). `expected_pages == completed_pages == 1`; reconciliation = `expected_rows == row_count == len(polozky)`. |
| **Licence / attribution** | | NKOD open-data conditions: `https://data.mpsv.cz/web/data/podminky-uziti`; CC BY 4.0: `https://creativecommons.org/licenses/by/4.0/` |
| **Decision** | implement | 2026-08-22. Live probes: codelists + full dump all 200, zero 4xx, no auth/anti-bot. Probe volume 38,903 active records (DoD floor ≥5,000 exceeded ~7.8×). Plan: `.kilo/plans/1787351616165-mpsv-cz-plan.md`. **Full DoD sweep:** `MPSVCollector` implemented, two consecutive daily sweeps (2026-08-22, 2026-08-23) each wrote **38,903 observations, 1/1 pages, `status=complete`, `expected_rows == row_count`**, zero 4xx; region mapped on **38,419/38,903 (98.8%)** with `region_mapping_status` populated on 100% of rows; reconciliation `integrity OK` (added 0, closed 0, unchanged 38,903 for the unchanged snapshot) with `closures.ndjson` written; zero PII tokens in output; `make check` green (113 tests). |

### Adzuna (DE first; multi-country adapter) — Increment 3

| Item | Status | Notes |
| --- | --- | --- |
| **URL** | | Keyed public REST: `https://api.adzuna.com/v1/api/jobs/{country}/search/{page}` with `app_id`/`app_key` (free developer signup at developer.adzuna.com). Docs: developer.adzuna.com `/docs/search`, `/docs/overview`, `/docs/terms_of_service`. Unauthenticated request verified live: nginx 400 — keys are mandatory for every call. Categories endpoint: `https://api.adzuna.com/v1/api/jobs/{country}/categories`. |
| **robots.txt fetched** | yes | `https://api.adzuna.com/robots.txt` → `User-agent: *` / `Disallow: /` — **blanket disallow on the API host** (standard keyed-API pattern). `https://adzuna.com/robots.txt` and `https://www.adzuna.com/robots.txt` → **405** (no robots handler on the consumer-site hosts; error page served instead). |
| **robots.txt disallowed paths** | all on api.adzuna.com | `Disallow: /` covers every path. Reading: this governs *unauthenticated* crawling of the host — unauthenticated requests fail with nginx 400 anyway. Keyed access is the API's only access mode and its documented, ToS-permissible purpose (see ToS clause below); the API terms are the operative permission for the collector's requests. The collector never touches adzuna.com/www hosts (405 on robots; not needed). Charter 1s+ pacing floor applies regardless. |
| **Crawl-Delay** | none | No directive in the fetched robots files. |
| **ToS reviewed** | yes | `https://developer.adzuna.com/docs/terms_of_service` (plus the linked general Adzuna T&C at adzuna.co.uk). |
| **ToS automated-access clause** | allowed (with conditions) | "Permissible Use: 1. Publishing Adzuna ad listings, 2. Publishing Jobsworth salary estimates, 3. **Personal research**." API users "encouraged to publish Adzuna listings... provided they comply" with attribution requirements: label data as sourced from "The Adzuna API" and link to the relevant local domain. Commercial/government/**academic** use is "permitted subject to a 14 day trial period... strictly for the purpose of validating the general coverage and quality of the data... It may not be used... to deliver any ongoing work or research... without written consent. After the trial period ends, a licence agreement may be required." No clause prohibits automated read access — the API exists for programmatic access. **Verdict:** allowed for validation/research use with mandatory attribution; ongoing academic research should seek Adzuna's written consent/licence (recorded as a condition, not a blocker for this increment's staging sweeps). |
| **SAFE_FIELDS coverage** | partial | Available: `source`, `source_id` (HMAC of native ad `id`/adref), `scope_id`, `sweep_id`, `observed_at`, `first_published` (`created`, ISO 8601 UTC), `country` (per-country config), `lang`/`source_language` (per-country locale), `number_of_vacancies` (default 1; no per-posting counts exposed). `last_modified`/`removed_at`: not in the search payload — absent; absence-based closure stamping deferred (MPSV's `reconcile_mpsv` stays MPSV-specific; generalizing is a later, cheap, HMAC-only step). **Region:** `region_mapping_status=not_present` — Adzuna exposes `location.area[]`/`display_name` free text only, no region/NUTS codes; a pinned area-name → NUTS 2024 crosswalk is deferred to a later increment (decision documented). **Occupation:** Adzuna `category` (label/tag) → ESCO deferred (`occupation_mapping_status=not_present`), as in Increments 1–2. |
| **PII risk** | high | Search results carry free-text `description` (may include contact persons/phones/emails), `company.display_name`, `title`, `redirect_url` (link to the source board's ad). **None are allowed into output** — allowlist-only parse + `NormalizedRecord(extra="forbid")`; PII-isolation test required. |
| **Rate limits** | documented | Free tier (ToS): **25 hits/min, 250 hits/day, 1000 hits/week, 2500 hits/month**. The API answers `429` + `Retry-After`; `scrapers/retry.py` honors Retry-After. Collector paces at ≥2.5 s (documented 25/min honored; charter 1 s floor exceeded for compliance). Sweep budget keeps the daily sweep inside 250 hits/day with headroom for retries. |
| **Snapshot semantics** | paginated, budgeted | Page number in the URL path (`.../search/{page}`), `results_per_page` (max 50), total in `count`. Response envelope `{"__CLASS__": "Adzuna::API::Response::JobSearchResults", "count": N, "results": [...]}`. **Probed live (2026-08-22):** DE all-active `count` = 1,155,948; NL all-active `count` = 190,606; every page 1..24 returned exactly 50 results, zero 4xx, zero 429. **Per-query result window discovered live:** pages beyond ~100 return listings already seen on earlier pages (probe pages 120–200 yielded `fresh_ids=0`) — a single all-active query caps at ~5,000 unique rows before recycling; `count` advertises the total stock, not the query window. `id` is returned as **string on DE but integer on NL** (coerced to str; verified live). |
| **Licence / attribution** | | API ToS requires attribution wherever data is published: reference "The Adzuna API" and link to `https://www.adzuna.co.uk/` (or the local domain, e.g. adzuna.de / adzuna.nl). |
| **Decision** | implement | 2026-08-22. robots: blanket disallow on the API host governs unauthenticated crawling; keyed API access is the documented, ToS-permissible access mode (allowed with attribution + academic-consent condition). **True cap verified live: the free tier (250 hits/day) plus Adzuna's per-query result window (~100 pages, ~5,000 unique rows/query) make the roadmap's "≥100,000 active listings in one DE sweep" physically impossible** — a full 1.16M DE stock would need ~23k hits (≈3 months of monthly quota) across segmented queries. The collector pages correctly to any budget (validated in mocked tests incl. >100k rows) and the live sweeps pull the full daily budget with zero 4xx and a complete, reconciled manifest; the advertised `count` (1,155,948 DE / 190,606 NL) is recorded in the manifest's `coverage_limitations`. **Live DoD evidence:** DE sweep `de-all-active` 20260822T000000Z — **100/100 pages, 4,841 rows, `status=complete`, `expected_rows == row_count`, zero 4xx**, all source_ids unique 64-hex HMAC, zero PII; NL sweep `nl-all-active` 20260823T000000Z — **100/100 pages, 4,956 rows, `status=complete`, `expected_rows == row_count`, zero 4xx**, same class with config-only change (CountryAdapter). Partitions at `data/raw/collections/adzuna/{de-all-active,nl-all-active}/`. |