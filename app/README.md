# The observatory app (Plan A v2)

The friendly, charts-first surface of the EU job-market observatory. It is a **renderer**,
not an analyser.

## The one rule

The app reads **`app/data.json`** and nothing else. It imports no duckdb, no dbt, no raw
partitions, and it computes no statistic: if a number is not in the export, it is not
shown. Regenerate the export from the repository root with:

```
make export-app
```

Verification that the rule holds (run from the repository root, PowerShell):

```powershell
Select-String -Path app\src\*.ts,app\src\*.tsx,app\src\components\*.tsx -Pattern "^\s*import "
Select-String -Path app\src\*.ts,app\src\*.tsx,app\src\components\*.tsx -Pattern "\.json|fetch\(|duckdb|dbt|\.parquet|\.csv|\.sql"
```

The second command must return exactly one hit: `data.ts: import data from '../data.json'`.

## Honesty laws the UI enforces

- **No cross-scope figure.** Every card and every chart shows exactly one
  `(source, scope_id)`. Nothing is pooled, added, or compared across countries.
- **Denominators travel with rankings** — region bars state the mapped total from
  `denominators.region`; requirement stacks state the posting total.
- **Gaps stay gaps.** The trend chart uses a real calendar axis and inserts an explicit
  break where sweeps are more than a day apart, so the Swedish 13-day hole can never
  render as a smooth line. Churn always states its spacing (`days_apart`).
- **Suppression is respected.** A bucket flagged `suppressed` in the export is never drawn
  as a zero; it is marked as suppressed.
- **Absence is a statement, not an empty chart.** Where a source publishes no field (the
  German occupation/skill/requirement gaps, detected from
  `denominators.*.postings_with_source_value == 0`), the app renders an honest
  "not available" card.
- **Motion is decorative and gated.** Entrance, hover and bar-grow animations live in
  `styles.css`; chart draw-in is a Chart.js animation option. Both switch off entirely
  under `prefers-reduced-motion` (the CSS media query plus the
  `usePrefersReducedMotion()` hook in `src/motion.ts`, which the charts read).
- **Loading and failure are states, not blank screens.** The app (and the export chunk
  with it) is lazy-loaded in `src/main.tsx`: a branded loading screen shows while it
  arrives, and an error boundary explains a failed load in plain language.
- **The audit page is one click away.** `src/links.ts` exports `AUDIT_PAGE_URL`
  (`../index.html`), assuming the recommended publish layout: this app's build output
  at `docs/app/` beside the audit page at `docs/index.html`.

## Stack

Node.js (preflight recorded in `SESSIONS.md`: v24.14.0) → Vite + React + TypeScript,
Chart.js via react-chartjs-2, `chartjs-adapter-date-fns` for the calendar axis.

```
npm install     # once
npm run dev     # local dev server
npm run build   # type-check + production build into app/dist (gitignored)
```

`app/data.json` and the source are committed; `app/dist/` and `node_modules/` are not.
The frozen analytical/audit page still lives at `docs/index.html` and is unaffected by
anything in this directory.
