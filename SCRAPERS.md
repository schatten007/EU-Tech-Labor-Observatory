# SCRAPERS Lab Charter

This worktree is the **scrapers lab**. It builds ethical crawlers that read
easy-to-scrape public job boards (German regional and public boards first) and
write their output into the shared `data/` tree of the observatory.

This charter is the governing document of this worktree. It supersedes any
inherited, stale, or contradictory instructions. The main repository's rules
about offline-only operation, single-source scope, or German collection do not
apply here. The main project's documents (`AGENTS.md`, `USER_MANUAL.md`,
`FUNCTIONALITY_ROADMAP.md`, `SOURCE_FEASIBILITY.md`) are not part of this
worktree; decisions recorded there are history for the main project only.

## What this worktree is

- A permission-granting lab: **network access is allowed and expected**. Fetching
  public pages and public APIs is the job of this worktree.
- Building scrapers, crawlers, and collectors for public job boards is in scope.
- The only output is NDJSON observation files plus manifest files under
  `data/raw/collections/`, shared on disk with the main checkout.
- The scraper code lives under `scrapers/` with its own `pyproject.toml` and
  `Makefile`.

## Scope decision (2026-08-31): breadth and repeat observations, not census

The observatory's published views need **breadth and repeat observations**,
not exhaustive counts: a top-25 region table, a per-sweep denominator, and
flow/survival series keyed by scope. A one-shot census cannot populate the
survival views at any size; only repeat sweeps of a frozen panel can. The
German census (`de-stock-segmented`) is therefore **cancelled, not deferred**
(`SCRAPER_ROADMAP.md` — Germany step 2a), and the BA Jobsuche lane is
re-planned as a frozen 400-region NUTS-3 panel (roadmap step 2b). Because
cross-source counts are never summed downstream, a second German source adds
a non-additive column: StepStone and Kimeta are cut on that basis, Indeed
stays a charter never-build, and other-country re-sweeps are conditional on
the observatory's live-service budget only.

Rules that follow from this decision and bind every repeat-observation sweep:

1. **Frozen panel.** The query set must be byte-identical across sweeps, with
   the seed recorded. Membership drift between sweeps fabricates closures and
   corrupts survival durations.
2. **Cancel means cancel.** Never resume a cancelled scope: a long gap
   followed by resumption records a mass fake `inferred_absence` closure spike
   downstream, because closures are inferred from any later sweep of the same
   scope.
3. **Weekly cadence by design.** Survival resolution can never be finer than
   the sweep interval and postings live ~30 days, so panels are designed for
   weekly re-sweep; the observatory may later run as a live service at weekly
   cadence, and monthly sweeps serve only as a demand snapshot.

## Golden rules (mandatory)

1. **robots.txt first.** Before touching a site, fetch and read `robots.txt`.
   Never request a path the robots file disallows for your user-agent, and honor
   any `Crawl-Delay` directive.
2. **Pacing.** Never pace requests faster than **one request per second** per
   target, whatever robots.txt says. Back off on `429`/`Retry-After` and respect
   documented rate limits.
3. **Terms of Service.** Review each target's ToS for automated-access clauses
   before building anything. Record the outcome (allowed / restricted /
   prohibited) in `SCRAPER_FEASIBILITY.md`. Never hide or skip this review.
4. **No personal data.** Never collect or write names, emails, phone numbers,
   free-text descriptions, or any field that identifies a person. Extraction is
   allowlist-only (see the SAFE_FIELDS contract below).
5. **Pseudonymize identifiers.** Source-native IDs are HMAC-SHA256
   pseudonymized with the shared `OBSERVATORY_HMAC_KEY` from `.env`, kept
   identical to the main project so pseudonyms stay consistent. Native IDs never
   leave this worktree.
6. **Output contract.** One JSON object per posting per NDJSON line, plus one
   manifest per sweep, exactly matching the schemas below.
7. **Verify before finishing.** `make check` (lint + types + tests) must pass.
8. **Never weaken the main gate.** Nothing built here may touch the main
   checkout, and nothing may make the main project's `make check` easier.

## Directory layout

```
scrapers/                       scraper code (httpx, beautifulsoup4, lxml)
tests/                          scraper tests
Makefile                        lab build targets
pyproject.toml                  lab dependencies (uv-managed)
SCRAPERS.md                     this charter
SCRAPER_FEASIBILITY.md          per-target feasibility records
.env                            shared OBSERVATORY_HMAC_KEY (never committed)
```

Output, gitignored and shared on disk with the main checkout:

```
data/raw/collections/<source>/<scope>/<partition_id>/
    observations.ndjson
    manifest.json
```

## Output contract: observations.ndjson

One line per posting. The fields are the SAFE_FIELDS allowlist; they mirror the
main project's `stg_postings.sql` so the main checkout can consume them without
changes.

| Field | Type | Notes |
| --- | --- | --- |
| `source` | string | lower-case source slug, e.g. `interamt` |
| `source_id` | string | HMAC-SHA256 hex digest of the native id; never the native id |
| `scope_id` | string | stable identifier of the query/region scope |
| `sweep_id` | string | one per run |
| `observed_at` | string | ISO 8601 UTC sweep timestamp |
| `first_published` | string \| null | source-reported first-publication timestamp |
| `last_modified` | string \| null | source-reported modification timestamp |
| `removed_at` | string \| null | source-reported removal timestamp |
| `nuts_code` | string \| null | NUTS 2024 code, e.g. `DE300` |
| `nuts_label` | string \| null | region label |
| `region_mapping_status` | string | `mapped` / `ambiguous` / `low_confidence` / `unmapped` / `not_present` |
| `region_mapping_method` | string | method that produced the mapping |
| `nuts_version` | string | `NUTS-2024` |
| `country` | string | ISO 3166-1 alpha-2, e.g. `DE` |
| `esco_occupation_uri` | string \| null | ESCO 1.2.1 occupation URI |
| `esco_occupation_label` | string \| null | occupation label |
| `occupation_mapping_status` | string | as `region_mapping_status` |
| `occupation_mapping_confidence` | string \| null | confidence when the source provides one |
| `occupation_mapping_method` | string | mapping method |
| `source_language` | string | language of the source content |
| `jobtech_taxonomy_version` | string | `v30`, or empty for non-JobTech sources |
| `esco_version` | string | `1.2.1` |
| `skill_mappings` | array | skill mapping objects (URI + status) |
| `lang` | string | content language code |
| `number_of_vacancies` | integer | advertised vacancies for the posting |

**Never present in output:** title, description text, employer, contacts, URLs,
native identifiers, street addresses, postcodes, or any free text.

## Output contract: manifest.json

One manifest per sweep. Mirrors the main project's `stg_collection_manifests.sql`.

| Field | Type | Notes |
| --- | --- | --- |
| `source` | string | source slug |
| `scope_id` | string | stable scope identifier |
| `scope_hash` | string | hash of the scope parameters |
| `scope_json` | string | the scope parameters as JSON (query, filters, country) |
| `partition_id` | string | partition identifier |
| `sweep_id` | string | one per run |
| `run_id` | string | run identifier |
| `observed_at` | string | ISO 8601 UTC sweep timestamp |
| `started_at` | string | ISO 8601 UTC run start |
| `completed_at` | string | ISO 8601 UTC run completion |
| `status` | string | must be `complete` for the main checkout to load it |
| `expected_pages` | integer | pages the sweep planned to fetch |
| `completed_pages` | integer | pages actually fetched |
| `expected_rows` | integer | rows the source advertised |
| `row_count` | integer | rows actually written; must equal the NDJSON line count |
| `hmac_key_version` | string | version of the HMAC key used |
| `source_version` | string | source/version identifier |
| `licence_reference` | string | URL or reference for the source licence |
| `access_method` | string | e.g. `robots-permitted-html` or `public-api` |
| `approval_status` | string | `approved` once the feasibility checklist passes |
| `expected_country` | string | ISO alpha-2 the scope filters to |
| `freshness_threshold_hours` | integer | freshness window for this source |
| `coverage_limitations` | string | documented limitations of the sweep |
| `reference_hashes` | string | hashes of reference tables used |
| `nuts_version` | string | `NUTS-2024` |
| `jobtech_taxonomy_version` | string | `v30`, or empty |
| `esco_version` | string | `1.2.1` |

Reconciliation: `status == "complete"`, `expected_pages == completed_pages`,
`expected_rows == row_count`, and `row_count` equals the number of lines in the
co-located `observations.ndjson`.

A within-stratum page cap is part of the declared scope, not an implementation
secret: it must be encoded in `scope_json` and stated in
`coverage_limitations` (e.g. "stratified region-bounded sample, not a
census"), so the reconciliation identities above hold **for the declared
capped scope**. A collector that caps at k pages and writes
`expected_pages == completed_pages == k` without declaring the cap passes
every downstream test while silently truncating — that pattern is forbidden
(scope decision 2026-08-31).

## Feasibility gate

A target is implemented only after its row in `SCRAPER_FEASIBILITY.md` is
complete and shows: permissive robots.txt, a ToS outcome that does not prohibit
automated read access, and the fields needed for SAFE_FIELDS. If a target is
prohibited, record that and drop it; do not route around it.

## Environment

- `.env` holds the shared `OBSERVATORY_HMAC_KEY`, kept identical to the main
  checkout so pseudonyms are consistent.
- `uv` is the package manager; lab dependencies are in the local
  `pyproject.toml`.
- `.kilo/setup-script.ps1` copies `.env` from the main checkout and runs
  `uv sync` on worktree creation.
