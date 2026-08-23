# EU Tech Labour Observatory

A quiet, aggregate record of public technology job-posting demand in Europe, published as one
self-contained static HTML page. Everything is reproducible offline: the only commands that touch
the network are the ones that collect data.

The observatory does not estimate, model, or interpolate. It publishes what a public job-posting
source actually said, with the denominator beside every ranking, the pinned reference versions
beside every mapped figure, and unresolved values shown as their own rows rather than dropped.

## Status

- **Sources:** JobTech Development / Arbetsförmedlingen `JobSearch` (Sweden), keyword scope. No
  German source has passed the approval gate yet — see `SOURCE_FEASIBILITY.md` for the six-criteria
  review and the verdicts.
- **Data:** 8 stored sweeps, the latest carrying 628 postings across 7 pages.
- **Published dimensions:** postings by country and NUTS region, ranked ESCO occupations and skills,
  employment type, working-hours type, contract duration, posting survival and flows, mapping
  quality, coverage and freshness.
- **Reference data, all pinned:** NUTS-2024, JobTech Taxonomy v30, ESCO 1.2.1. Methodology version
  1.2 is stamped in the page footer and in every CSV export.

## Quick start

```sh
uv sync          # install the locked environment (the only step that needs the network)
make check       # the offline gate: lint, types, 63 Python tests, mapping evaluation, 190 dbt resources
make site        # build site/build/index.html from the committed synthetic sample
```

Open `site/build/index.html` in any browser. There is no server, no port, no login, and no build
configuration to edit.

| Command | What it does | Network |
| --- | --- | --- |
| `make check` | The quality gate. Never touches the network, by design. | Never |
| `make site` | Rebuilds the page from the committed synthetic sample. | Never |
| `make live-site` | Rebuilds the page from stored collection partitions. | Never |
| `make release-check` | Inspects the built page against the publication rules. | Never |
| `make sweep` | Collects one complete sweep from the live source. | Yes |
| `make reference` | Rebuilds the pinned crosswalks from the JobTech Taxonomy API. | Yes |

## How it works

1. **Collect** — `scripts/collect.py` reads one complete sweep page by page and stores it as an
   append-only partition beside a manifest of expected and observed rows. Stored partitions are
   never rewritten, so a posting that disappears becomes an event rather than a deletion.
2. **Enrich** — `scripts/enrich.py` maps structured geography, occupation, skill, and requirement
   fields onto the pinned references. Free text is never classified.
3. **Sanitize** — `scripts/sanitize.py` is the privacy boundary: it pseudonymises the native posting
   id under a versioned HMAC secret and keeps only allowlisted fields. Posting text, employer names,
   URLs, and native identifiers never cross it.
4. **Transform** — dbt builds views only (`transform/`), each under an enforced column contract with
   data tests.
5. **Publish** — `scripts/publish.py` queries those views and writes one static page: no external
   assets, no analytics, no network access at build time, and no JavaScript required to read it.

## Repository layout

```
scripts/          collector, enrichment, privacy boundary, publisher, evaluation, release check
transform/        dbt models, contracts, and data tests
data/reference/   pinned crosswalks: NUTS, JobTech->ESCO occupation and skill, requirement labels
data/sample/      committed synthetic sample and the mapping quality report
data/raw/         stored collection partitions - private, append-only, never committed
tests/            one offline test module and its fixtures
site/build/       the generated page - not committed, rebuild it with make site
```

## Privacy and licensing

Only aggregates are published. Native identifiers, source URLs, employer names, and posting text are
absent by construction rather than removed afterwards. Small-count suppression applies to the
posting-flow and survival views; latest-sweep distributions are published in full and are
single-dimension only, never cross-tabulated.

Code is MIT licensed (`LICENSE`). Source data stays under its own licence: aggregates derived from
JobTech Development / Arbetsförmedlingen may be republished with attribution, while posting text and
identifiers may not, and are not available here.

## Development log

`SESSIONS.md` records every increment: what was built, what was measured, what was deliberately not
done, and the gate result. It is the project's memory — read the most recent entries before changing
anything.
