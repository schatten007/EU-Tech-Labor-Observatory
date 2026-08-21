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
