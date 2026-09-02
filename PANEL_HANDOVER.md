# BA Jobsuche NUTS-3 panel — handover and operations reference

Status: **lab work complete, sweep operations delegated.** This document is the
handover for the frozen NUTS-3 panel (`de-nuts3-panel`, roadmap step 2b) built in
this worktree on 2026-09-02. Sweeps 2–5 and the ongoing weekly cadence run in the
**main project after the merge**, not here.

Authority: this file is operational guidance only. `SCRAPERS.md` (charter) wins on
every rule, then `SCRAPER_ROADMAP.md`, `SCRAPER_SOURCE_LANDSCAPE.md`,
`SCRAPER_FEASIBILITY.md`, `SESSIONS.md`. Nothing here relaxes the charter.

---

## 1. What exists

| Artifact | Location | Notes |
| --- | --- | --- |
| Panel definition (pinned) | `data/reference/ba_panel_nuts3.json` | 400 entries, membership hash `545b162ec6e5fbdc…`. **Committed. Never regenerate.** |
| Panel module | `scrapers/ba_panel.py` | frame, candidates, membership hash, scope params, side-file writer |
| Collector mode | `scrapers/ba_jobsuche.py` — `_fetch_panel`, `parse_search_envelope` | declared page cap, plan from advertised totals, locality assertion, HMAC dedupe, 403 cooldown |
| CLI | `python main.py --source ba --panel --date <YYYY-MM-DD>` | `make scrape-ba-panel` wraps it |
| Acceptance gate | `make check-ba-panel` → `scripts/check_ba_panel_readiness.py` | one line per assertion, all panel partitions |
| Pinning tool (one-off, already run) | `scripts/pin_ba_panel.py` | only for a *new* panel generation; see §5 |
| Sweep 1 | `data/raw/collections/ba/de-nuts3-panel/20260902T080422Z/` | accepted, DoD met |

Sweep 1 result: 400 regions queried, **1,315/1,315 pages**, `status=complete`,
`expected_rows == row_count == NDJSON lines = 28,900`, **393/400 NUTS-3 regions**
mapped, zero failed requests (25 absorbed 403 throttles), PII scan clean, 270
regions at the declared cap, per-region advertised totals summing to **372,413**.

---

## 2. Publish decision (2026-09-02): publish `de-nuts3-panel`, archive the other two

The main app accepts **one scope per push** (`scripts/publish.py:756`
`_verify_single_scope`), so exactly one of the three stored BA scopes can be the
published German BA surface. Measured from the stored partitions themselves
(reproduce by re-running the aggregation in §7):

| Scope | Partitions | Rows (distinct ids) | Mapped | NUTS-3 with ≥1 mapped row | Top-25 share of mapped rows | Re-sweepable? |
| --- | --- | --- | --- | --- | --- | --- |
| `de-all-window` | 1 | 10,000 (10,000) | **64.48%** | 358/400 | 40.2% | yes, but membership is whatever the unscoped query returns → drifts between sweeps |
| `de-stock-segmented` | 65 | 203,674 (183,028) | 99.77% | **124/400** | 48.1% | **never** — cancelled 2026-08-31 |
| `de-nuts3-panel` | 1 | 28,900 (28,900) | 98.97% | **393/400** | 9.5% | **yes — frozen membership, weekly by design** |

**Decision: the panel is the published German BA scope.** It is the only scope
that serves all three published surfaces at once:

* **Regional breadth** — 393/400 regions, against 358 (window, at 64% mapping) and
  124 (census, which went deep in a few regions and never reached breadth).
* **Per-sweep denominator** — the panel is the only scope that records an
  authoritative per-region stock (`suchergebnis.maxErgebnisse`, stored per region
  in `panel_regions.json`). Neither other scope has one.
* **Flow and survival series** — these need repeat observations of a **stable**
  query set. The census is cancelled and can never be re-swept; the unscoped
  window's membership changes between sweeps, so closures inferred from it would
  be fabrications. The panel is the only survival-capable German scope.
* **Mapping quality** — 98.97% mapped, effectively matching the census's 99.77%
  and far ahead of the window's 64.48%.
* **No main-side change required** — publishing one scope satisfies
  `_verify_single_scope` as it stands.

The other two scopes stay as **archived lab evidence**: not published, not
re-swept, not deleted. `de-stock-segmented` remains the best static measurement of
German active stock (183,028 distinct postings) and is cited as such in
`SCRAPER_FEASIBILITY.md`; `de-all-window` remains the honest record of the
10,000-listing query-window bound.

### Mandatory caveat for whoever wires the regional surface

**Do not build the top-25 region table from panel row counts.** Every region is
capped at 4 pages × 25 = 100 rows, and 270 of 400 regions hit that cap in sweep 1,
so row counts per region are flattened by construction — that is exactly why the
panel's top-25 share is 9.5% while the census's is 48.1%. The panel's row
distribution measures *sampled presence*, not demand.

The demand signal is the advertised total per region in
`panel_regions.json → regions[<nuts_code>].advertised` (372,413 across sweep 1).
Feed the regional table from those totals, or label the surface explicitly as a
capped sample. Cross-source counts are never summed, so this column must not be
added to Adzuna DE or any other source.

---

## 3. Runbook: sweeps 2–5, then weekly

One sweep per day for sweeps 2–5, then weekly. Each sweep is ~40 minutes
(~1,315 paced requests plus ~25 × 45 s throttle cooldowns).

```powershell
# 1. Gate first. A sweep collected with a broken mapping bakes the error into a
#    permanent partition.
make check

# 2. Sweep, output to a log. NEVER let a 40-minute sweep stream into a session.
make scrape-ba-panel *> logs/ba-panel-sweep2.log

# 3. Read only the tail.
Get-Content -LiteralPath logs/ba-panel-sweep2.log -Tail 8

# 4. Acceptance: one line per assertion, across ALL panel partitions.
make check-ba-panel
```

`make scrape-ba-panel` uses `$(shell date -u +%Y-%m-%d)`, which needs a GNU `date`
on PATH. On Windows PowerShell without it, call the CLI directly:

```powershell
uv run --offline python main.py --source ba --panel --date 2026-09-03 *> logs/ba-panel-sweep2.log
```

If a shell or session may be interrupted, start it as a tracked background process
instead of a foreground command; sweep 1 was lost once to a cut foreground turn and
had to be restarted from scratch.

### Acceptance criteria (unchanged from the DoD)

`make check-ba-panel` must print six PASS lines:

1. every partition `status=complete`, `expected_pages == completed_pages`,
   `expected_rows == row_count == NDJSON line count`;
2. every sweep covers **≥ 390 of 400** NUTS-3 regions;
3. **one** membership hash across all partitions, equal to the pinned artifact;
4. **zero** failed requests (absorbed 403 throttles are throttle events);
5. PII scan clean;
6. page cap declared in `scope_json` **and** in `coverage_limitations`.

After sweep 5 the third assertion is the important one: the same
`545b162ec6e5fbdc…` must appear for all five partitions. A second hash means the
panel drifted and the survival series built from those sweeps is invalid.

### Cadence

Weekly. Survival resolution can never be finer than the sweep interval and
postings live ~30 days, so a monthly sweep degrades to a demand snapshot with no
usable survival curve. Daily is unnecessary and multiplies throttle exposure.

---

## 4. Never do this

* **Never re-sweep, mutate, resume, or delete `de-stock-segmented`.** It is
  cancelled, not paused. Closures are inferred from any later sweep of the same
  scope, so a sweep after this gap would record a mass fake `inferred_absence`
  closure spike across 183,028 postings.
* **Never run `make scrape-ba-segmented`** and never pass `--fresh` for the BA
  source.
* **Never edit or regenerate `data/reference/ba_panel_nuts3.json`** between sweeps.
  It is the frozen membership. Editing it silently converts real postings into
  fake closures and corrupts survival durations.
* **Never rebuild the German crosswalk** (`make reference-germany`) mid-series
  without re-pinning and starting a new panel generation — the artifact is
  validated against that reference.
* **Never remove the declared page cap from `scope_json` or
  `coverage_limitations`.** Capping at k pages while writing
  `expected_pages == completed_pages == k` without declaring the cap is forbidden
  by the charter: it passes every downstream test while silently truncating.
* **Never sum panel counts with Adzuna DE** or any other source.

---

## 5. Failure playbook

| Symptom in the log or gate | Meaning | Action |
| --- | --- | --- |
| `ba_throttle_observed` warnings | BA's Apache-edge token bucket answered 403; the collector waited 45 s and retried | Normal. ~25 per sweep. Not a failure. |
| `RuntimeError: … 403 again after a 45 s throttle cooldown` | Hard block, sweep aborts, **no partition written** | Do not retry immediately. Wait hours, then re-run. Verify pacing is still 1 s. |
| `ba_panel_locality_mismatch` for a few regions | BA resolved a same-name place elsewhere | Tolerable at sweep-1 levels (2 regions). A sudden jump means BA's place resolver changed — investigate before accepting the sweep. |
| Breadth assertion drops below 390 | regions stopped yielding rows | Do **not** re-pin to fix it. Check `panel_regions.json` for regions with `advertised: 0`; a broad collapse indicates a source change, a single-region drop is normal churn. |
| `missing_envelope` non-zero in `panel_regions.json` | `suchergebnis.maxErgebnisse` no longer parses → **schema drift** | **Reject the sweep and delete the partition.** Each affected region planned only 1 page instead of up to 4, so the sweep is silently truncated even though it reconciles. See §6, issue 1. |
| Sweep interrupted mid-run | no partition written, nothing persisted | Re-run from the start. Partial sweeps are never written. |
| Gate reports two membership hashes | the panel drifted | Stop. Do not publish. Identify which partitions used which hash; a mixed series cannot produce valid closures. |

### If the panel must be re-pinned (new generation)

Only when BA's place resolver changes so much that breadth cannot be met.
Re-pinning starts a **new panel generation** and breaks comparability:

1. `python scripts/pin_ba_panel.py` (probes candidates, reuses prior evidence).
2. Treat the result as a new scope or a documented generation boundary — the
   survival series **restarts**; never mix generations under one scope.
3. Record the new hash, the reason, and the boundary date in
   `SCRAPER_FEASIBILITY.md` before any sweep.

---

## 6. Known issues and accepted risks

Recorded 2026-09-02 from a branch review. **All are accepted as-is for now** — none
blocks sweep 2 or the publish decision — but they are the first places to look if
the panel behaves oddly later.

1. **Envelope drift is detected but not asserted** (`scrapers/ba_jobsuche.py:804`,
   `scripts/check_ba_panel_readiness.py:175`). If `parse_search_envelope` stops
   finding `suchergebnis.maxErgebnisse`, `panel_missing_envelope` is incremented and
   the region's page plan silently stays at 1 page instead of up to 4. The manifest
   still reconciles and the gate still passes, so a sweep can lose roughly two
   thirds of its rows while reporting `status=complete`. **Mitigation until fixed:
   read `missing_envelope` in `panel_regions.json` after every sweep and reject the
   partition if it is non-zero.** Fix is a few lines in the checker.
2. **Breadth is measured from row codes, not from queried regions**
   (`scripts/check_ba_panel_readiness.py:130`). Region attribution partly comes from
   city-name resolution, which is independent of the query, so a row collected under
   region A can be attributed to neighbouring region B. In sweep 1, 399 queried
   regions produced rows but only 393 distinct codes appeared. The ≥390 bar can in
   principle be met by leakage while queried strata stay empty. `panel_regions.json`
   already records the query-side truth (`regions_with_rows`); check both.
3. **The locality rule exists twice** (`scripts/pin_ba_panel.py:65` duplicates
   `BAJobsucheCollector._panel_locality_ok`). The pinning tool decides what enters
   the frozen panel with its own copy. If either changes, a pinned query can be one
   the collector then flags as a mismatch. The collector's copy is authoritative.
4. **`build_panel()` runs three times per sweep** (`main.py:254`, `:424`, `:966`),
   so the manifest's `membership_hash` and the query list actually swept come from
   three independent reads of the artifact. Harmless while the artifact is
   read-only; it does mean the code does not *prove* they are the same panel.
5. **A missing `panel_regions.json` is misreported** (`scripts/check_ba_panel_readiness.py:139`)
   as a cap-declaration failure, and because failed-page counts are read only from
   that file, the "zero failed requests" assertion would pass vacuously for such a
   partition.
6. **DE231 (Amberg-Sulzbach) can never contribute rows.** No candidate query in the
   frame has stock, so query-side coverage is capped at 399/400 permanently. This is
   why the bar is 390, not 400.
7. **Sweep data is gitignored** (`.gitignore: data/*`, with `data/reference`
   excepted). The 28,900-row sweep-1 partition and the 65 census partitions exist
   only on the machine that produced them. If those partitions matter, copy them out
   of the lab before the worktree is removed.

---

## 7. Reference

Reproduce the publish-decision numbers (aggregate output only — never print NDJSON
lines or manifest bodies into a session):

```powershell
uv run --offline python -c "
import json
from collections import Counter
from pathlib import Path
root = Path('data/raw/collections/ba')
for scope in ('de-all-window', 'de-stock-segmented', 'de-nuts3-panel'):
    parts = sorted(p for p in (root/scope).iterdir() if (p/'manifest.json').exists())
    ids=set(); nuts=Counter(); status=Counter(); rows=0
    for p in parts:
        with (p/'observations.ndjson').open(encoding='utf-8') as fh:
            for line in fh:
                if not line.strip(): continue
                r=json.loads(line); rows+=1; ids.add(r['source_id'])
                status[r['region_mapping_status']]+=1
                if r['region_mapping_status']=='mapped' and r.get('nuts_code'): nuts[r['nuts_code']]+=1
    print(scope, len(parts), rows, len(ids), status.get('mapped',0), len(nuts))
" *> logs/de-scope-comparison.log
```

Panel-specific metadata per sweep lives in
`data/raw/collections/ba/de-nuts3-panel/<sweep_id>/panel_regions.json`:
`membership_hash`, `regions_queried`, `regions_with_rows`, `regions_empty`,
`regions_capped`, `regions_short`, `locality_mismatches`, `missing_envelope`,
`failed_pages`, `throttle_events`, `duplicates_dropped`, and per region
`{form, query, advertised, rows, pages, planned_pages, resolved_place, search_mode}`.

Probe scripts kept as evidence for how the design was chosen:
`scripts/probe_ba_envelope.py` (total-hits field), `scripts/probe_ba_region.py`
(`wo=` addressing forms), `scripts/probe_ba_resolve.py` (why tile postcodes are not
a sound region key). Their findings are recorded in `SCRAPER_FEASIBILITY.md`
(probes E1–E6); re-running them is not part of any sweep.
