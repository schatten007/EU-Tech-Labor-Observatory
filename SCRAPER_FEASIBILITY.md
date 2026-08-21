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