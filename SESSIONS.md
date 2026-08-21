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
