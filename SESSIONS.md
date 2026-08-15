# Implementation Sessions

Each increment is completed in one session. Keep unfinished work in the next row rather
than expanding the active increment.

| Increment | Session | Status | Scope | Check |
| --- | --- | --- | --- | --- |
| 1 | 2026-08-13 | Complete | Review the Phase 0 scaffold and establish a passing offline baseline. | `make check` passed |
| P1 | 2026-08-13 | Complete | Isolate raw responses and add the minimum PII sanitization boundary. | `make sample && make check` passed |
| 2 | 2026-08-13 | Complete | Add the smallest raw observation collector against ignored private responses. | Offline collector check passed |
| 3 | 2026-08-13 | Complete | Point staging at collected observations while preserving its contract. | `make sample && make check` passed |
| 4 | 2026-08-13 | Complete | Derive posting presence and closure events. | `make sample && make check` passed |
| 5 | 2026-08-13 | Complete | Publish one minimal labour-demand view. | `make site` passed |
| 6 | 2026-08-15 | Complete | Add reliable, resumable, immutable JobTech query sweeps. | `make sample && make check && make site` passed |
| 7 | 2026-08-15 | Complete at feasibility boundary | Review DE/SE sources; add approved-source metadata, coverage, and freshness without unsupported German collection. | `make sample && make check && make site` passed |

## Session Notes

### 2026-08-13 - Increment 1

- Reviewed all source, configuration, schema, and SQL files without opening datasets or
  fixtures.
- Kept this increment to baseline correctness; no collector or dashboard scaffolding.
- Fixed formatting, test collection, dbt CLI argument order, repository-relative DuckDB
  paths, staging timestamp type, and enforceable key null checks.
- Added one small check proving the default probe command does not access the network.
- Enforced offline dependency resolution for every command in `make check`.
- Rebuilt the committed sample offline because its existing schema predated the sample
  builder's explicit projection.
- Final result: `make check` passed with one Python test and six dbt resources passing.

### 2026-08-13 - Privacy Increment P1

- Added `scripts/sanitize.py` as the only privacy boundary: normalized NDJSON enters,
  allowlisted analytical NDJSON leaves.
- Pseudonymized source IDs with HMAC-SHA256 and a required 32-character
  `OBSERVATORY_HMAC_KEY`; stable IDs preserve longitudinal joins without publishing
  native identifiers.
- Kept dates, coarse geography, occupation, language, skill URIs, and vacancy counts.
  Dropped all unspecified fields, including title, description, employer, contacts,
  organization number, URL, city, and postcode.
- Moved future live probe responses from tracked fixtures to ignored `data/raw/probe/`
  and removed the four committed live-response fixtures.
- Replaced the sample builder's fixture dependency with two synthetic rows and removed
  title, employer, and text from the staging contract.
- Deliberate boundary: skill extraction from private text must happen before sanitizing;
  only normalized skill URIs cross into analytical data.
- Final result: `make sample && make check` passed with two Python tests and six dbt
  resources passing.

### 2026-08-13 - Increment 2

- Added the offline JobTech collector for recorded raw responses.
- Normalized source dates, country, language, vacancy count, and observation time.
- Applied the existing sanitizer before writing NDJSON, so native IDs and private fields
  never leave the collector boundary.
- Final result: `make check` passed with three Python tests and six dbt resources
  passing.

### 2026-08-13 - Increment 3

- Replaced the source-native Parquet sample with sanitized observation NDJSON generated
  through the same normalization and privacy boundary as collected responses.
- Pointed staging at `OBSERVATIONS_PATH`, with the committed synthetic sample as its
  offline default.
- Preserved the ten-column staging contract and observation grain; staging now only
  selects and casts collector fields.
- Standardized script commands on `python -m scripts...` so package imports work without
  path manipulation.
- Final result: `make sample && make check` passed with three Python tests and six dbt
  resources passing.

### 2026-08-13 - Increment 4

- Added one event view: each observation becomes a presence event and each posting may
  produce one closure event.
- Preferred source-reported `removed_at`; otherwise inferred closure at the first later
  complete source sweep where the posting is absent.
- Expanded the synthetic sample to cover persistence, reported closure, and inferred
  closure, with one exact-set survival test.
- Deliberate ceiling: each `(source, observed_at)` is a complete, consistently scoped
  sweep. Partial or partitioned collection needs a scope key before feeding this model.
- Final result: `make sample && make check` passed with three Python tests and eight dbt
  resources passing.

### 2026-08-13 - Increment 5

- Added one aggregate model: active postings by source and country at each source's
  latest complete sweep.
- Added a self-contained static HTML publisher using Python, DuckDB, and the standard
  library; no frontend framework, runtime JavaScript, external assets, or new dependency.
- Published only counts, source, country, and observation time. Native IDs and private
  posting text do not enter the aggregate or page.
- Added one offline publisher test and checked the built page at desktop and mobile
  widths with no page overflow, text overlap, or external requests.
- Final result: `make check && make site` passed with four Python tests and nine dbt
  resources passing.

### 2026-08-15 - Iteration 6

- Added serial JobTech pagination with a canonical query scope, bounded transient retries,
  `Retry-After` support, durable page checkpoints, and resumable collection state.
- Added immutable timestamped partitions, atomic publication, content hashes, run locks,
  exact-rerun idempotency, and explicit complete/failed sweep manifests.
- Added source/scope/sweep provenance to privacy-safe observations and publishable demand
  aggregates without allowing native identifiers or private source fields through.
- Gated staging, latest demand, and inferred closures on complete same-scope manifests;
  failed, partial, orphaned, and zero-row sweeps now have explicit tested behavior.
- Kept live collection opt-in through `make sweep` and preserved the network-free sample,
  quality gate, and static-site build.

### 2026-08-15 - Iteration 7

- Approved JobTech JobSearch for the fixed Swedish keyword scope based on its official API
  and CC0 publication; recorded source version, licence, access method, expected country,
  freshness threshold, and limitations in every new manifest.
- Rejected BA Jobsuche because BA terms prohibit automated collection, kept HR-BA-XML
  exploratory because it requires an agreement and does not document a national read feed,
  rejected EURES without formal partner access, and classified the official BA statistics
  API as aggregate-only.
- Did not implement or simulate German posting collection and did not label the product as
  Germany-Sweden complete.
- Added deterministic source coverage/freshness models, strict Swedish country validation,
  zero-row country coverage, and source-separated publication with no combined total.
