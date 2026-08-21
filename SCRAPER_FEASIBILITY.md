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