# UI Redesign — Design Specification

**Owner:** UI/design-specialist pass, per `.kilo/plans/1788493260000-ui-redesign-design-brief.md` (Plan 2).
**Written:** 2026-09-04. **Status:** complete for review; implementation is a separate increment.
**Measured against:** `docs/index.html` as committed 2026-09-04 (`data-built` 2026-09-04 16:44 UTC,
methodology 1.4), `scripts/publish.py`, `scripts/release_check.py`, `scripts/insights.py`.
**Prototype:** `design/prototype/index.html` (static, no JavaScript, non-build path; illustrative
subset with real published figures).

> **SUPERSEDED IN PART, 2026-09-05 (owner decision).** The owner judged the implemented
> "quiet instrument" direction "dry, bland and technical for an average user". The
> **aesthetic chapters of this spec (§1.1–§1.3, §1.8) are superseded** by
> `.kilo/plans/1788618000000-dynamic-user-friendly-presentation-plan.md`: dynamic charts,
> plain language, tables demoted. The **accessibility chapters (§5) and the release-rule
> mapping (§5.4) REMAIN BINDING**, as do every data-honesty law the spec obeys (per-scope
> separation, counts-not-ratios, denominators, suppression). Read this spec for its
> structure and a11y, not for its taste.

> **Measurement drift, stated up front.** The plan's §0 figures were measured against an earlier
> build. A Swedish sweep ran after the plan was written: the committed artefact now shows
> **623 postings, Fresh, 9 complete sweeps** for `jobtech / jobtech-f5cf1d409aa51fad` and still
> **28,900 postings, Stale (67 h against 24 h)** for `ba / de-nuts3-panel`. None of the plan's four
> design failures is value-dependent — typed absence, hero comparability, freshness legibility, and
> mapping strength are failures of *state rendering*, not of today's numbers. This specification
> designs the state machine; every copy example below uses the current artefact's real values, and
> the prototype proves both a stale lamp (DE) and a fresh lamp (SE) side by side.

---

## 1. Design plan

### 1.1 Subject grounding

The subject is **an observatory: an instrument that records what it can see and states the edges of
its own vision.** Its vernacular is measurement — frames, coverage, thresholds, censoring, panels,
denominators, annunciators. The design draws on that vernacular directly:

- **Instrument plates.** Every collecting scope is rendered as a labelled, bordered plate — a
  bounded region with its own frame of reference. Nothing spans plates; nothing pools between them.
- **Annunciator lamps.** Freshness and coverage use aviation-annunciator semantics: green
  *operating*, amber *caution*, red *fault*. Stale is amber, never red, because stale data is still
  valid data; red is reserved for genuine faults (partial coverage).
- **A data register.** All numbers speak in a monospaced register — the voice of a log printer —
  so every figure is tabular by construction and reads as recorded, not as marketed.
- **A mark vocabulary for the instrument's own limits.** Four marks — filled, hollow, hatched,
  dashed — encode the four epistemic states of any figure on the page. The marks are the design
  system's core idea and appear in the signature element, the table cells, and the absence states.

Audience and page job are taken from the plan §1 unchanged: a technically literate
non-specialist; the page's single job is to make a sampled, partially mapped, two-scope
observation legible without flattening its caveats into decoration.

### 1.2 Palette

The established deep-green identity is **kept and refined, not replaced** — the observatory already
owns it, and the meaningful upgrade this redesign makes is semantic (annunciator lamps, mark
vocabulary), not cosmetic. Six named core values; state tones are functionally derived and frozen.

| Token | Hex | Role |
| --- | --- | --- |
| **Housing Green** | `#163D2C` | The instrument housing: header plate, plate borders, nav ground, link-adjacent brand tone. |
| **Signal Green** | `#27845B` | Counted / reached marks: frame-strip ticks, relative-volume bars, lamp-fresh family. Non-text only beside its printed value. |
| **Caution Amber** | `#EFB744` | Housing accent rule and the focus indicator (always paired with an ink ring; see §5.2). Bright amber never carries text and never sits unbordered on white. |
| **Ink** | `#17201C` | Primary text on ground and panel. |
| **Ground / Panel** | `#F4F6F5` / `#FFFFFF` | Page ground; plate and table surfaces. |
| **Soft Ink** | `#4C5B54` | Secondary text, hollow-mark strokes, unknown-lamp tone. |

Derived state tones (all pre-existing on the live page, retained verbatim): `--ok-bg #E3F0E9` /
`--ok-ink #14543A`; `--warn-bg #FBEED2` / `--warn-ink #6A4703`; `--err-bg #FBE7E4` /
`--err-ink #7A2318`; `--line #CBD3CF`; `--line-soft #E1E6E3`; `--link #12543B`;
`--brand-ink #DFEAE4`. Two new functional tones: **hatch stroke** `#6F8178` (the withheld mark)
and **unknown-bg** `#E9EDEA`. Lamp glyph fills are the dark lamp tones `#14543A` (fresh),
`#6A4703` (stale), `#4C5B54` (unknown) on their chip grounds — computed ratios in §5.1.

Why amber stays: amber is the caution colour of instrumentation. The page's most important
recurring state — *stale but valid* — needs a colour that says "mind the age", not "something
broke". Bright `#EFB744` keeps its two safe jobs (accent on the dark housing; focus indicator when
ringed in ink) and yields its on-panel signalling to the darker lamp tones that pass contrast.

### 1.3 Typography — three voices

No web fonts (hard constraint). Three roles from system stacks, each with a job in the
instrument metaphor:

| Role | Stack | Use |
| --- | --- | --- |
| **Data Register** (display + all numerals) | `ui-monospace, "Cascadia Mono", "SF Mono", Consolas, "Roboto Mono", Menlo, monospace` | The `<h1>`, scope identifiers, every count, age, threshold, date, and code. Monospace makes tabular alignment structural, not a `font-variant-numeric` hope. |
| **Panel Label** (eyebrow/utility) | `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`, 600–700, uppercase, tracking `+0.05em`–`+0.08em`, `.72–.78rem` | Table headers, stat labels, plate eyebrows, lamp chip text, section labels. The voice of engraved panel labels. |
| **Body** | The same system-ui stack at 400/500, `16px/1.5`, measure ≤ 78ch | All prose: definitions, denominators, insights, absence sentences. |

The `<h1>` is set in the Data Register, uppercase with `+0.08em` tracking — a stamped data plate,
not an editorial masthead. Type scale: `h1` 1.9rem mono; `h2` 1.3rem; `h3` 1.02rem; `h4` .92rem
(Panel Label voice); body 1rem; count cells .92rem mono; stat readouts 1.6rem mono.

### 1.4 Layout concept

One measured column, `min(1080px, 100% − 32px)`, as today. Inside it:

- **The header plate** (housing green, amber rule) and the **mode selector** (the existing tab bar,
  restyled; behaviour unchanged — JS-enhanced tabs, stacked no-JS).
- **The observation board** — the only multi-card region on the page. One instrument card per
  `(source, scope_id)`, in a `repeat(auto-fill, minmax(320px, 1fr))` grid at desktop, stacked at
  tablet and mobile. Cards are bounded plates; no element crosses card boundaries.
- **Scope plates** — the repeated structural unit inside Countries, Occupations, and Requirements:
  a bordered plate whose header names exactly one `(source, scope_id)` and whose body holds only
  that scope's surfaces. Scope separation becomes structural and visible rather than an `h3`.
- Tables keep their scroll-region wrappers, captions, and CSV controls; ranks, denominators, and
  unlisted-tail sentences stay in their gate-mandated adjacency.

### 1.5 The signature element: the region-frame strip

Region breadth — the project's most distinctive figure — becomes a **unit-tick strip**: one tick
per region in the pinned NUTS-3 frame; a filled tick is a region with at least one mapped posting,
a hollow tick is a region inside the frame that the sweep did not reach.

```
DE · ba / de-nuts3-panel        frame = 400 NUTS-3 regions
▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▯▯▯▯▯▯
393 of 400 DE NUTS-3 regions have at least one mapped posting.

SE · jobtech / keyword scope    frame = 21 NUTS-3 regions
▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮
21 of 21 SE NUTS-3 regions have at least one mapped posting.
```

Design properties, each tied to a constraint:

- **Counts, never a ratio.** The strip draws `regions_in_frame` discrete units and fills
  `regions_with_postings` of them. The printed sentence stays the existing breadth sentence,
  verbatim. No percentage exists anywhere near it.
- **No geometry, no map.** The strip is generated from two integers by a loop; it is arrangement,
  not geography. It needs no external asset.
- **No shared axis.** Strip length equals frame size (400 vs 21 units) — a fact about
  administrative geography, not about demand. Strips are left-anchored inside their own plates,
  never aligned to a shared right edge, never stacked, never on one baseline.
- **Both halves visible.** The reached and the unreached are both drawn; 7 hollow ticks at the end
  of the German strip are as legible as 393 filled ones.
- **Degradation ladder.** Tick pitch is `clamp(container / frame, 1.5px, 28px)`. Below a 1.5px
  pitch (mobile, 400-unit frames) the strip coarsens to a proportional two-segment bar with ruler
  graduations every 50 units — form stays "units on a scale", counts text unchanged. 21-unit frames
  stay resolvable at every width down to 320px and never coarsen.
- **Honest SVG.** Server-rendered inline SVG, `role="img"`, `aria-label` carrying the breadth
  sentence, `<desc>` explaining the tick semantics. Emission: frames of ≤ 60 units render one
  `<rect>` per tick; larger frames render an SVG `<pattern>` that *defines one tick as a cell*
  and two pattern-filled runs (filled run of `regions_with_postings` cells, hollow run for the
  rest) plus ruler graduations. The pattern cell keeps the unit grain — every 4px of the strip is
  one region — at ≈0.3 KB of markup instead of ≈12 KB. The prototype's two strip forms
  (per-tick for SE, pattern for DE) are both emitted as plain f-string templates; no dependency.

### 1.6 The mark vocabulary

Four states, one key, used everywhere a figure's epistemic status matters:

| Mark | State | Meaning | Where it appears |
| --- | --- | --- | --- |
| **Filled** (solid `#27845B`) | Counted | Observed and published. | Frame-strip ticks, bar cells, "fresh/covered" lamp family. |
| **Hollow** (1.5px `#4C5B54` stroke, no fill) | In frame, not reached | Inside the pinned frame; the sweep observed no mapped posting. | Frame-strip ticks, `Not stated` row markers. |
| **Hatched** (`#6F8178` diagonal strokes) | Withheld | A real group of 1–4 postings, suppressed for disclosure control. Never interpolated. | Suppressed cells, suppressed-group row labels, sparkline gap annotations. |
| **Dashed plate** (1.5px dashed `#4C5B54` border) | Structurally absent | The source publishes no field for this, so nothing can be observed. | Absence plates. |

States are encoded by **form first, tone second** — filled vs hollow vs hatched vs dashed are
distinguishable in greyscale and to a colour-blind reader; tone differences are reinforcement
only. The mark key is rendered once, in Overview → "How to read this page", as four swatch-plus-
sentence rows (copy in §3.5); the suppression definition in Survival and Governance cross-refers
to it in prose, as today.

### 1.7 Wireframes (desktop)

```
┌ housing plate ────────────────────────────────────────────────────────────┐
│ EU TECH LABOUR OBSERVATORY                          methodology 1.4      │
│ Where technology postings are advertised, …          built 2026-09-04 …   │
└──────────────────────────────── amber rule ───────────────────────────────┘
[ Overview ][ Status ][ Countries ][ Occupations ][ Requirements ][ Survival ]…
┌ Overview ─────────────────────────────────────────────────────────────────┐
│ lede (unchanged copy)                                                    │
│ ┌ Observation board ──────────────────────────────────────────────────┐   │
│ │ ┌ plate: ba / de-nuts3-panel · DE ──── [● Stale·67h/24h][● Covered]┐│   │
│ │ │ 28,900  postings · observed 2026-09-02 00:00 UTC · this scope   ││   │
│ │ │ ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▯▯▯▯▯▯                                     ││   │
│ │ │ 393 of 400 DE NUTS-3 regions have at least one mapped posting.  ││   │
│ │ │ · 1 complete sweep — too few unsuppressed buckets to state a    ││   │
│ │ │   direction                                                     ││   │
│ │ └──────────────────────────────────────────────────────────────────┘│   │
│ │ ┌ plate: jobtech / … · SE ──────── [● Fresh·0h/48h][● Covered] ────┐│   │
│ │ │ 623  postings · observed 2026-09-04 18:39 UTC · this scope      ││   │
│ │ │ ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮                                            ││   │
│ │ │ 21 of 21 SE NUTS-3 regions have at least one mapped posting.    ││   │
│ │ │ 〰 sparkline (own scale, gaps preserved) 〰  Daily · 9 sweeps    ││   │
│ │ └──────────────────────────────────────────────────────────────────┘│   │
│ └────────────────────────────────────────────────────────────────────┘   │
│ How to read this page: mark key (4 marks) + workflow (unchanged)          │
│ Insights digest (unchanged sentences, per-scope labels)                   │
│ [table-overview-demand] (restyled: count column in Data Register)        │
└───────────────────────────────────────────────────────────────────────────┘
```

```
┌ Countries → NUTS regions ─────────────────────────────────────────────────┐
│ [table-countries-demand] (unchanged columns, restyled)                    │
│ ┌ scope plate: ba / de-nuts3-panel ──────────── [● Stale][● Covered] ───┐ │
│ │ frame strip + breadth sentence + manifest caveat (definition)         │ │
│ │ denominator sentence (class="denominator", unchanged position)        │ │
│ │ [table-countries-regions-ba-de-nuts3-panel]                          │ │
│ └───────────────────────────────────────────────────────────────────────┘ │
│ ┌ scope plate: jobtech / … ────────────────────────────────────────────┐ │
│ │ … same anatomy, 21-of-21 strip …                                      │ │
│ └───────────────────────────────────────────────────────────────────────┘ │
┌ Occupations and skills ───────────────────────────────────────────────────┐
│ section definitions (unchanged copy)                                      │
│ ┌ scope plate: jobtech / … ────────────────────────────────────────────┐ │
│ │ Occupation ranking  [▮▮▮▮▯ 526 mapped · 623 carry · 623 in sweep]    │ │
│ │   denominator → [table-occupations-ranked-…]                          │ │
│ │ Technology skills   [▮▯ 25 mapped · 45 carry · 623 in sweep]          │ │
│ │   denominator → [table-occupations-skills-…]                          │ │
│ │ Mapping quality → [table-occupations-mapping-…]                       │ │
│ └───────────────────────────────────────────────────────────────────────┘ │
│ ┌ scope plate: ba / de-nuts3-panel ────────────────────────────────────┐ │
│ │ ┄┄ Occupation ranking — structurally absent ┄┄  (absence plate)       │ │
│ │ ┄┄ Technology skills — structurally absent ┄┄   (absence plate)       │ │
│ │ Mapping quality → [table-occupations-mapping-…]                       │ │
│ └───────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────┘
```

### 1.8 Self-critique pass

What was revised after checking the plan against this brief, and why:

1. **The hero.** First instinct was the template answer: one big number, small label, supporting
   stats — which on this page is precisely failure #2 ("largest single observation" beside Sweden's
   count, inviting the comparison the page forbids). Revised to the observation board: one bounded
   instrument card per scope, each with its own count, its own frame strip, and its own trend
   state. No pooled number exists above, between, or below the cards.
2. **Breadth as a figure.** First instinct was a donut or a "coverage %" — both violate the
   no-new-ratio constraint (breadth is "393 of 400", never 98%), and a donut implies a map-like
   whole the repo deliberately does not have. Revised to the unit-tick strip, which draws the
   counts themselves.
3. **Stale ≠ red.** First instinct kept the current warn/err badge pair and reached for red to
   make staleness louder. Rejected: stale data is valid data; red is reserved for genuine faults
   (partial coverage). Amber caution semantics, with the word and both numbers always present.
4. **Dashboard grid.** An early layout sketch used a 12-column dashboard grid with a KPI row —
   the exact "dashboard convention" the brief names as wrong for this subject. Revised to one
   measured column with plates; the board is the only card region.
5. **Broadsheet drift.** A hairline-rules-everywhere pass looked disciplined but landed on the
   generic "hairline broadsheet" default. Revised: structural borders are 1.5px plate borders;
   internal rules stay soft (`--line-soft`); the ruled-graduation motif lives on the strips, where
   it means something.
6. **Serif display.** The first type sketch used Georgia for display — readable anywhere, specific
   nowhere, and editorial rather than instrumental. Revised to the monospaced Data Register for
   `h1` and all numerals: the page's most repeated content *is* recorded numbers, and the register
   voice makes tabular alignment structural.
7. **Section merges.** Considered merging Status into Data quality (both operational). Rejected:
   they answer different questions ("is it current?" vs "what is imperfect?"), the merge saves
   little, and every slug must stay addressable anyway. All nine sections keep their slugs; the
   visual language unifies them.

---

## 2. Layout specification

### 2.1 Breakpoints

| Breakpoint | Width | Behaviour |
| --- | --- | --- |
| Desktop | ≥ 1000px | Board cards in a 2-up grid (`auto-fill, minmax(320px, 1fr)`); tables at full column width inside their scroll regions. |
| Tablet | 600–999px | Board cards stack to one column; everything else unchanged (tables already scroll horizontally inside `role="region"` wrappers). |
| Mobile | < 600px | Single column; header plate compacts (h1 1.25rem, summary wraps); frame strips coarsen per the §1.5 ladder when tick pitch would fall below 1.5px; filter fields go full-width (existing behaviour). |

The tab bar (mode selector) wraps to two rows at narrow widths, as today. Tabs, filters, and CSV
remain JS enhancements; with JavaScript disabled the page is the stacked rendering of §4.

### 2.2 Global frame

- **Header plate:** housing green; `h1` in Data Register caps; the one-line description and the
  "Last successful update…" summary unchanged in copy; amber bottom rule retained (the housing
  accent). Build stamp and methodology version move into the footer only (they are already there;
  the header stops repeating them).
- **Mode selector:** the existing tab bar, restyled as instrument mode labels (Panel Label voice,
  amber underline on the active mode). Behaviour, markup pattern, and `data-tab`/`data-panel`
  wiring unchanged — this redesign does not touch the tab machinery.
- **Footer:** unchanged copy; numerals in Data Register.

### 2.3 Section by section

Each entry names the surfaces rendered, the `(source, scope_id)` each block belongs to, and what
changes. "Unchanged" means copy and data wiring; styling changes are global (Data Register
numerals, Panel Label headers, plate borders).

**Overview** (`#overview`)
- Lede: unchanged.
- **Observation board** (new): one card per `(source, scope_id)` from `labour_demand_latest` ∪
  `source_coverage` (card order = demand order, largest first, as today's scope keys). Card
  anatomy: plate header (scope label in Data Register + country code) → annunciator row
  (freshness lamp, coverage lamp) → count readout (`active_postings`, mono 1.6rem) with observed
  timestamp and sublabel "active postings · this scope only" → frame strip + breadth sentence →
  trend line (per-scope finest-grain series from `posting_flows`, own scale, gap semantics) or the
  typed no-trend state. Every element belongs to exactly one scope; nothing aggregates.
- "How to use this page": workflow list (unchanged copy) joined by the **mark key** (§3.5).
- Insights digest: unchanged sentences and per-scope labels.
- Definitions and `table-overview-demand`: unchanged columns and rows; the "Largest single
  observation" stat is **removed** (its job is the board's now); the remaining stats ("Last
  successful update", "Trend direction", "Source coverage") stay as readouts — they are
  instrument-state metadata, not market figures, and their copy already says so.

**Status** (`#status`)
- Insights, lede, definitions: unchanged.
- Stats readouts: unchanged five (they describe the instrument, not the market).
- `table-status-runs`: unchanged columns, including the "What this means" run-state sentence; restyled.
  The annunciator row above the table is the same lamp component as the board's, so Status and
  Overview cannot disagree visually.

**Countries** (`#countries`)
- Definition and `table-countries-demand`: unchanged (the within-source relative-volume bar, its
  label, and the "Within-source only" column stay exactly as gated).
- **NUTS regions:** one scope plate per `(source, scope_id)`. Plate body order, top to bottom:
  frame strip → breadth sentence (`class="definition"`) → manifest caveat (`class="definition"`,
  verbatim) → denominator sentence (`class="denominator"`, verbatim, immediately before its table)
  → `table-countries-regions-<scope-slug>`. This is today's order plus the strip and the plate
  chrome; nothing moves relative to the gate.

**Occupations and skills** (`#occupations`)
- The three section definitions: unchanged copy.
- Per scope plate, in order: **Occupation ranking** (mapping-strength chip in the table's
  block-head; denominator; `table-occupations-ranked-<scope-slug>`) → **Technology skills** (chip;
  denominator; `table-occupations-skills-<scope-slug>`) → **Mapping quality**
  (`table-occupations-mapping-<scope-slug>`).
- For a scope whose source publishes no structured field (`postings_with_source_value = 0`), the
  ranked table is **replaced** by an absence plate (§3.9) carrying the existing
  empty-by-construction sentence. The denominator readout ("Ranked from 0 mapped of 28,900 …")
  is retained inside the plate as its "drawn from" line — the draw is stated even when the draw
  is empty. Mapping quality still renders (the German scope has real region mapping outcomes).
- Scope insight sentences render inside their scope's plate, above the rankings, as today.

**Requirements** (`#requirements`)
- Lede and definition: unchanged.
- Per scope plate: three sub-blocks in the existing order (Employment type, Working hours,
  Contract duration). For a scope with rows: the table renders unchanged (columns, `Not stated`,
  `Unrecognised code`, codes beside labels), with hollow-dot markers on `Not stated` rows and
  hatch markers on `Unrecognised code` rows. For a scope with no rows because the source publishes
  no such field: an absence plate replaces the table (typed copy in §3.9).
- No denominator sentences here (unchanged — none are required; the columns sum to the sweep by
  construction and the definition says so).

**Survival** (`#survival`)
- Insights, definitions, sparklines, `table-survival-basis`, `table-survival-flows`: unchanged in
  data and copy. Restyling: suppressed cells render "suppressed" on a hatched ground; true zeros
  render "0" on plain ground; the dash stays for absent duration statistics. Sparkline gaps keep
  their semantics; the existing `<desc>` already explains them.

**Data quality** (`#quality`)
- Definitions, `table-quality-coverage`, `table-quality-frequency`, and the per-scope
  "Missing and uncertain mappings" blocks: unchanged; each missing-mappings block moves inside its
  scope's plate chrome for consistency with Countries/Occupations.

**Methodology** (`#methodology`)
- Definitions list, provenance table: unchanged; restyled.

**Governance** (`#governance`)
- All blocks (licences, retention, privacy, disclosure control, architecture, snapshot,
  methodology version): unchanged copy; restyled.

### 2.4 Mobile and tablet sketches

```
Tablet (720px)                          Mobile (<600px)
┌───────────────────────────────┐       ┌───────────────────────┐
│ header plate                  │       │ header plate (1.25rem)│
│ [mode selector, wraps]        │       │ [mode selector, 2 rows]│
│ ┌ board card: ba/de ────────┐ │       │ ┌ board card: ba ────┐│
│ │ lamps / count / strip     │ │       │ │ lamps (wrap)       ││
│ │ trend state               │ │       │ │ count + date       ││
│ └───────────────────────────┘ │       │ │ strip (coarsened:  ││
│ ┌ board card: jobtech/se ──┐ │       │ │ ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▯   ││
│ │ …                        │ │       │ │  graduations /50)  ││
│ └───────────────────────────┘ │       │ │ trend state        ││
│ sections stacked; tables      │       │ └────────────────────┘│
│ scroll inside their wrappers  │       │ sections stacked;     │
└───────────────────────────────┘       │ tables scroll         │
                                        └───────────────────────┘
```

---

## 3. Component inventory

Copy is design material here; every state's sentence is specified verbatim. Sentences marked
*(existing)* are published copy retained unchanged — the redesign does not rewrite prose the
publisher already derives from data.

### 3.1 Scope plate

The bounded region for one `(source, scope_id)`. Anatomy: 1.5px housing border; header row with
the scope label **as an `h3`** (Data Register, e.g. `ba / de-nuts3-panel`, `translate="no"`) +
country code chip, and the annunciator row right-aligned; body with the section's surfaces. The
plate name must stay a real heading: the page's heading ladder is `h2` section → `h3` scope →
`h4` sub-block, exactly as the live page renders it today, and `release_check` fails skipped
levels — a plate header that is a styled `span` (the prototype's first attempt) reintroduces an
`h2`→`h4` skip under it.

| State | Rendering |
| --- | --- |
| Normal | As above. |
| No collecting scope | Fallback plate with today's "No collecting scope" label; no lamps, no strip. |

### 3.2 Annunciator (freshness and coverage lamps)

One chip per status; two chips per scope plate and per board card, always in the order
freshness → coverage. Chip = 8px square lamp + Panel Label text + numbers, on the chip ground.
Not colour-alone: the word is always present, and both numbers are always stated.

| Status | Copy | Lamp/ground |
| --- | --- | --- |
| Fresh | `Fresh · {age} h old · threshold {n} h` | `#14543A` on `#E3F0E9` |
| Stale | `Stale data · {age} h old · threshold {n} h` | `#6A4703` on `#FBEED2` |
| Unknown freshness | `Unknown freshness · no threshold recorded` | `#4C5B54` on `#E9EDEA` |
| Covered | `Covered · {observed:,} of {expected:,} rows` | `#14543A` on `#E3F0E9` |
| Partial coverage | `Partial coverage · {observed:,} of {expected:,} rows` | `#7A2318` on `#FBE7E4` |
| Unknown coverage | `Unknown coverage · approval or metadata incomplete` | `#4C5B54` on `#E9EDEA` |

Current-artefact examples: DE `Stale data · 67 h old · threshold 24 h` + `Covered · 28,900 of
28,900 rows`; SE `Fresh · 0 h old · threshold 48 h` + `Covered · 623 of 623 rows`.

### 3.3 Observation card (board)

Per-scope instrument card. Body order: count readout (`{active_postings:,}` in Data Register
1.6rem) → `{observed timestamp}` → sublabel `active postings · this scope only` → frame strip
(§3.4) with its sentence → trend block.

| Trend state | Rendering |
| --- | --- |
| Series with ≥2 unsuppressed buckets | Sparkline (own scale, gaps preserved) + grain label + `{complete_sweeps} complete sweeps`. |
| Fewer than 2 buckets | Typed state line: `1 complete sweep — too few unsuppressed buckets to state a direction` (uses the existing direction phrase; the count is `complete_sweeps`). |
| No flows published | Typed state line: `no trend published for this scope`. |

### 3.4 Region-frame strip

Unit-tick figure per §1.5. States:

| State | Rendering |
| --- | --- |
| Frame pinned, partial reach | Ticks: `regions_with_postings` filled, remainder hollow; sentence *(existing)*: `{with:,} of {in_frame:,} {country} NUTS-3 regions have at least one mapped posting.` |
| Frame pinned, full reach | All ticks filled; same sentence form (`21 of 21`). |
| No frame pinned | No strip; *(existing)* degraded sentence: `No NUTS-3 frame is pinned for this country in the reference data, so no breadth count is published.` |
| No breadth row | *(existing)*: `No region breadth was published for this scope, so no breadth count is stated.` |
| Narrow viewport (pitch < 1.5px) | Two-segment proportional bar with graduations every 50 units; sentence unchanged. |

`aria-label` = the breadth sentence; `<desc>` = `One tick per region in the pinned NUTS-3 frame;
filled ticks are regions with at least one mapped posting, hollow ticks are regions the sweep did
not reach.`

### 3.5 Mark key

Rendered once in Overview → "How to read this page", as four rows (swatch + sentence):

- **Filled** — `Counted: observed and published by this sweep.`
- **Hollow** — `In the frame, not reached: within the pinned reference frame, with no mapped posting.`
- **Hatched** — `Withheld: a real group of 1 to 4 postings, suppressed for disclosure control.`
- **Dashed** — `Structurally absent: the source publishes no field for this, so nothing can be observed.`

The key is prose and marks, no table; it carries no `denominator` class.

### 3.6 Denominator readout

The `class="denominator"` paragraph, verbatim copy, verbatim position (immediately before its
ranked table, nothing denominator-classed in between). Restyle only: Data Register numerals, a
2px signal-green left tick beside it, `max-width: 78ch`. Existing sentences *(existing)*, e.g.
`Ranked from 526 mapped posting(s) of 623 in the latest sweep; 623 carry a structured occupation.
Only the 25 most frequent occupations are listed below, accounting for 519 of those mapped
postings; the rest sit in an unlisted tail.`

### 3.7 Mapping-strength chip

Attached to the table it qualifies — inside the table's block-head row (beside the CSV control),
after the denominator, never carrying the `denominator` class. A three-segment micro-figure
(mapped = filled; carries a field but unmapped = hatched; no field = hollow) scaled within the
dimension's own `postings_total`, plus printed counts:

- Occupation (SE): `526 mapped · 623 carry the field · 623 in the sweep`
- Skill (SE): `25 mapped · 45 carry the field · 623 in the sweep`
- Occupation (DE): no chip — the absence plate replaces the ranking.
- `aria-label`: `Mapping strength: {mapped:,} of {total:,} postings mapped; {with_value:,} carry a
  structured {noun} field.` (repeats the denominator's numbers, which is the point).

### 3.8 Ranked table

Existing tables `table-countries-regions-*`, `table-occupations-ranked-*`,
`table-occupations-skills-*` with captions, scoped headers, `data-row` filter attributes, CSV
control, and both empty states. Changes: Data Register count cells; the within-source bar and its
`% of this source's largest scope` label unchanged (existing, gated); rank numbers in Data
Register. Empty-because-filtered state *(existing)*: `Every row in this table is hidden by the
current filters.`

### 3.9 Absence plate (structurally absent)

Replaces a ranking or distribution table when the source publishes no structured field for the
dimension. Anatomy: 1.5px dashed `#4C5B54` border; a wide dash glyph; eyebrow in Panel Label
voice; the typed sentence; the "drawn from" line.

| Surface | Eyebrow | Sentence |
| --- | --- | --- |
| Occupation ranking | `Occupation ranking — structurally absent` | *(existing)* `This source publishes no structured occupation field for this scope, so no posting here can be mapped to an ESCO occupation: the ranking is empty by construction, not by a mapping failure.` |
| Technology skills | `Technology skills — structurally absent` | *(existing)* `This source publishes no structured skill field for this scope, so no posting here can be mapped to an ESCO skill: the ranking is empty by construction, not by a mapping failure.` |
| Employment type | `Employment type — structurally absent` | `This source publishes no structured employment-type field for this scope, so no employment-type distribution exists for any of its {total:,} postings: the table is empty by construction, not by a collection failure.` |
| Working hours | `Working hours — structurally absent` | `This source publishes no structured working-hours field for this scope, so no working-hours distribution exists for any of its {total:,} postings: the table is empty by construction, not by a collection failure.` |
| Contract duration | `Contract duration — structurally absent` | `This source publishes no structured contract-duration field for this scope, so no duration distribution exists for any of its {total:,} postings: the table is empty by construction, not by a collection failure.` |

The requirement sentences follow the established occupation/skill pattern deliberately: one voice,
data-derived, reusable by any future source with the same gap. The "drawn from" line inside the
plate keeps the existing denominator copy for rankings (`Ranked from 0 mapped posting(s) of
{total:,} in the latest sweep; 0 carry a structured {noun}.`); requirement plates omit it (no
denominator exists for them, and none is required).

### 3.10 Count cell states (suppression)

Applies to `table-survival-basis` and `table-survival-flows` only.

| State | Rendering |
| --- | --- |
| Count ≥ 5 | `{value:,}` on plain ground. |
| Suppressed group | The word `suppressed` on a hatched ground (CSS `repeating-linear-gradient`, `#6F8178` strokes). |
| True zero | `0` on plain ground — deliberately indistinguishable in weight from any other count, and never hatched. |
| Statistic not computable | `—` (existing dash). |

Row labels carrying a suppressed group keep *(existing)* `(suppressed group)`; the definition
above the table and the Governance disclosure paragraph keep the `1 to 4` sentence verbatim
(gate-checked).

### 3.11 Distribution table (requirements)

Existing tables `table-requirements-*` for scopes with rows. Changes: Data Register count cells;
`Not stated` rows get a hollow-dot marker before the label; `Unrecognised code` rows get a
hatched-swatch marker before the label. Columns, codes, and copy unchanged.

### 3.12 Sparkline

Existing `_sparkline` component: server-rendered inline SVG, `role="img"`, `aria-label`,
`<title>`/`<desc>`, gap semantics, dots for isolated buckets. Restyle: Data Register axis labels
if any are added (none today); polyline in Signal Green; gap explanation *(existing)* in `<desc>`.

### 3.13 Insight sentence

Existing `class="insight"` paragraphs, existing generated copy, existing per-scope labels.
Restyle: a 2px hollow tick in the left margin — insights are observed statements, not counted
figures, so their mark is hollow. (A quiet joke with a purpose: every mark on the page means
something.)

### 3.14 Filter bar, live region, CSV control, noscript

Existing behaviour and copy, restyled: Panel Label field labels; `Applying filters…` *(existing)*;
error state *(existing pattern)* `Filters could not be applied ({message}). Every row is shown
instead.`; live region *(existing)* `{n} rows shown; no filters hide anything.` The filter bar and
CSV buttons stay server-rendered `hidden` with their `data-*` enhancement attributes (gate-listed);
the noscript paragraph *(existing)* stays: `Filters, section tabs, and CSV download need
JavaScript. Every section and every row is already rendered below without it.`

### 3.15 Stat readout

The `dl.stats` blocks (Overview, Status): Panel Label terms, Data Register values, 2px signal
tick. Copy unchanged except the removed "Largest single observation" (§2.3).

### 3.16 Caveat paragraph

Existing `class="definition"` paragraphs (breadth sentences, manifest caveats, section
definitions): unchanged copy, unchanged class, restyled to body voice at `.9rem` with `max-width:
78ch`.

---

## 4. Annotated no-JS rendering

With JavaScript disabled the page is the full document, top to bottom, in this order (this is also
the DOM order with JS on — the script only ever *hides* non-active panels client-side and never
moves content):

```
skip link → header plate → mode selector (renders as 9 anchor links; they still
jump, because every section id exists) →
  [noscript note: filters/tabs/CSV need JS] →
  Overview   (board cards stacked; every number, strip, lamp, and sentence
              server-rendered; trend states are static text) →
  Status     (lamps, readouts, run table) →
  Countries  (demand table; scope plates with strips, breadth sentences,
              denominators, region tables) →
  Occupations(SE rankings with chips; DE absence plates; mapping quality) →
  Requirements (SE distribution tables; DE absence plates) →
  Survival   (sparklines as static SVG with title/desc; tables with
              hatched suppressed cells) →
  Quality / Methodology / Governance (tables and definitions) →
  footer.
```

What is *not* available without JS, by design: the filter form (server-rendered `hidden` with
`data-filters`), CSV buttons (`data-csv`), the loading/error/live regions (`data-loading`,
`data-error`, live region is empty until filters run), and single-panel tab focus. Nothing else is
hidden; the release check's `ENHANCEMENT_ATTRS` allowlist is unchanged, so the gate mechanically
proves this. The prototype (`design/prototype/index.html`) ships **without any script at all**,
so the screenshots in §7 double as evidence of the no-JS rendering.

---

## 5. Accessibility notes

### 5.1 Contrast (computed, WCAG 2.x)

Text pairs (need ≥ 4.5:1) — all pass:

| Pair | Ratio | | Pair | Ratio |
| --- | --- | --- | --- | --- |
| Ink `#17201C` / Ground | 15.36 | | warn-ink / warn-bg | 7.26 |
| Ink / Panel | 16.67 | | err-ink / err-bg | 8.48 |
| Soft Ink / Ground | 6.60 | | ink / warn-bg | 14.50 |
| Soft Ink / Panel | 7.16 | | ink / ok-bg | 14.21 |
| Link / Ground | 8.21 | | ink / err-bg | 14.01 |
| Link / Panel | 8.91 | | white / Housing | 12.08 |
| ok-ink / ok-bg | 7.59 | | brand-ink / Housing | 9.80 |

Non-text pairs (need ≥ 3:1) — all pass:

| Pair | Ratio | | Pair | Ratio |
| --- | --- | --- | --- | --- |
| Signal `#27845B` / Panel | 4.63 | | lamp-stale `#6A4703` / warn-bg | 7.26 |
| Signal / Ground | 4.26 | | lamp-fresh `#14543A` / ok-bg | 7.59 |
| Hollow stroke `#4C5B54` / Panel | 7.16 | | lamp-unknown / unknown-bg | 6.06 |
| Hatch stroke `#6F8178` / Panel | 4.13 | | Focus: amber vs ink ring | 9.15 |
| Hatch stroke / Ground | 3.80 | | ink ring `#17201C` / Panel | 16.67 |

Two known failures are designed out, not accepted:

1. **Bright amber on white fails 3:1 (1.82)** — so amber never fills a lamp and never outlines
   focus alone. Lamps use the dark lamp tones on chip grounds; the focus indicator is amber with
   an adjacent ink ring (below).
2. **White on Signal Green is only 4.63:1** — so no white text is ever set on a Signal Green
   fill; the green carries marks only, always with their values printed in ink nearby.

### 5.2 Focus

- Order: DOM order, which is reading order; the skip link is first. Scope plates and board cards
  are not focusable containers (their contents are), except the existing focusable table scroll
  regions (`role="region" tabindex="0"`), which keep `tabindex="0"` and their `aria-label`s.
- Document head: `<meta name="theme-color" content="#f4f6f5">` so browser chrome matches the
  ground (also a fix for the live page, which lacks it). Scope identifiers and source codes carry
  `translate="no"` so auto-translation cannot garble `jobtech-f5cf1d409aa51fad` or taxonomy
  codes.
- Visible focus everywhere: `:focus-visible { outline: 3px solid #EFB744; box-shadow: 0 0 0 1px
  #17201C; outline-offset: 1px; }` — the amber indicator is bounded by an ink ring, so the
  indicator meets 3:1 against *some* adjacent colour on every background on the page (amber vs ink
  9.15:1; ink ring vs panel 16.67:1; ink ring vs housing 12.08:1). Table scroll regions keep the
  inset outline (existing behaviour).
- Interactive elements: tabs (anchors), filter controls (labelled inputs/selects), CSV buttons —
  all keep their existing accessible names. Target sizes: controls ≥ 40×28px hit areas (padding
  ≥ 8px vertical); tab links ≥ 40px tall. `touch-action: manipulation` on tabs and buttons.

### 5.3 Reduced motion

The design introduces no animation. The one motion rule (existing) stays: under
`prefers-reduced-motion: reduce`, transitions and animations collapse to `.01ms`. There is no
page-load sequence, no scroll reveal, no ambient motion — an instrument at rest.

### 5.4 How each `release_check` rule is satisfied by construction

| Rule (scripts/release_check.py) | How the design holds it |
| --- | --- |
| One `h1`, no skipped heading levels | Header keeps the only `h1`; sections keep `h2`; scope plates keep `h3`/`h4` inside their sections; absence plates add no heading levels (their eyebrow is a `<p>`, not a heading). |
| Every table captioned, headers scoped | No table is added or de-captioned; absence plates are not tables. |
| Every control labelled | Filter labels unchanged; CSV buttons keep text labels; no new controls. |
| `alt` on images / `aria-label` on `role="img"` | Frame strips and sparklines are `role="img"` with `aria-label` + `<title>` + `<desc>`; no `<img>` is introduced. |
| Unique ids | New ids follow `strip-<scope-slug>` / `plate-<scope-slug>` patterns derived from the existing unique `_scope_slug`. |
| No external assets, allowlisted links only | No new fetch attributes; strips and marks are inline SVG/CSS; hatch via CSS gradient or a same-document `<defs>` pattern (`fill="url(#hatch)"` is a fragment reference, not a fetch). |
| Masked views present + suppression rules | Both masked tables keep their ids, columns, and `suppressed` wording; the hatch ground is decoration on the same text. |
| Ranked views present + denominator adjacency | All ranked tables that render keep their id prefixes; the denominator paragraph stays the last `denominator`-classed element before each; the mapping chip, block-head, and plate chrome carry no `denominator` class. Where an absent scope's ranked table is replaced by an absence plate, the page still contains each ranked prefix (the other scope renders it), which is what the gate checks. |
| `1 to 4` suppression sentence present | Suppression copy unchanged in Survival and Governance. |
| No secrets/emails | No new free-text content beyond the specified copy; scope ids and codes are the existing published ones. |
| Nine section slugs addressable | No slug changes; no merges. |
| Nothing server-rendered hidden without JS | Only the five `ENHANCEMENT_ATTRS` elements are server-rendered `hidden`; absence plates, strips, lamps, and cards are plain visible markup. |
| Insights non-empty + Overview digest | Insight rendering path untouched. |

### 5.5 Other accessibility floor items

- Not colour-alone: every state pairs form or text with tone — lamps carry words and numbers;
  marks differ by fill form; stale is never signalled by colour only.
- Numbers: Data Register everywhere, so tabular alignment is structural.
- Long scope ids (`jobtech-f5cf1d409aa51fad`) wrap at `/` boundaries (`overflow-wrap: anywhere` on
  the Data Register scope label) so they cannot blow out a plate at 320px.
- Table scroll regions: `overscroll-behavior: contain` so a horizontal table scroll does not
  hijack the page scroll on touch.

---

## 6. Implementation feasibility

For each proposed element: how it is emitted, and whether anything new is needed from the data
layer. Everything is hand-written HTML/CSS/SVG from Python string templates — no dependency, no
build step, no network — matching `publish.py`'s existing emission style.

| Element | Emission | New data? |
| --- | --- | --- |
| Scope plate | `f-string` wrapper reusing `_scope_slug` / `_scope_label` | No — same keys the publisher groups by today. |
| Annunciator lamps | Small helper mirroring `_badge`, reading `CoverageRow` fields already fetched (`freshness_status`, `freshness_age_hours`, `freshness_threshold_hours`, `expected_rows`, `observed_rows`, `coverage_status`). | No. |
| Observation board | Loop over `_scope_keys(demand)`; per-scope card body assembled from rows already fetched (`demand`, `coverage`, `region_breadth`, `flows`). | Minor refactor: `_finest_series` currently takes one scope's rows via the Overview "leading scope" pick; the board needs it per scope — a loop over the already-fetched `flows` list. No new query. |
| Region-frame strip | Helper `_frame_strip(with_postings, in_frame, country)` emitting one `<rect>` per tick in a loop (≈30 chars/tick; 400-tick strip ≈ 12 KB). | No — `RegionBreadthRow` already carries both integers. |
| Mark key | Static template string. | No. |
| Mapping-strength chip | Helper reading `MappingCoverageRow` rows already fetched; segments as three inline `<span>`s with percentage widths computed within `postings_total` (a rendering of existing counts, like the existing within-source bar). | No. |
| Absence plate | Helper beside `_empty_by_construction`, same condition source (`mapping_coverage_latest`), emitting the typed sentence + dashed plate instead of the table. | **Flag 1** — see below. |
| Suppressed-cell hatch | CSS class on the existing `suppressed` text (`repeating-linear-gradient`). | No. |
| `Not stated` / `Unrecognised code` markers | Conditional span in the existing requirement row loop, keyed on the existing `mapping_status`/label. | No. |
| Data Register / Panel Label / plate chrome | CSS token block replacing the current `STYLE` variables plus class additions; no structural HTML change. | No. |
| Focus ring | One `:focus-visible` rule. | No. |
| Header/footer/stat restyle | Template edits only. | No. |

**Flag 1 — the requirement absence condition.** The occupation/skill absence plates read
`mapping_coverage_latest` (`postings_with_source_value = 0`, `postings_total > 0`), which is
exactly how `_empty_by_construction` works today. For the three requirement dimensions the same
pattern needs `mapping_coverage_latest` to carry `employment_type` / `working_hours_type` /
`duration` rows for the German scope. If the view does **not** emit rows for dimensions a source
never offers, the implementation increment must either (a) extend `mapping_coverage_latest` to
emit a `postings_with_source_value = 0` row per required dimension (a dbt change, its own review),
or (b) derive the condition from `requirement_demand_latest` emptiness combined with a positive
`postings_total` from the demand row (weaker: cannot distinguish "no field" from "field present,
all values missing", but available without touching transform). The design's copy is written to be
true under either condition. **The implementer must verify which case holds before wiring the
sentence.**

**Flag 2 — per-scope trend on the board.** The board card's trend block reuses the existing
`_direction` text and the existing sparkline; the only change is calling them per scope rather
than for the single leading scope. No new figure is published — the same rows, rendered per scope.

**Flag 3 — no new published definitions.** Nothing in this design introduces a new metric,
ratio, or definition: the strip renders `regions_with_postings` / `regions_in_frame`; the chip
renders `mapping_coverage_latest`; lamps render `source_coverage` fields. Therefore no
`METHODOLOGY_VERSION` bump is required by the design itself. (Whether an implementation bump is
warranted is the implementer's call under the repo's versioning rule.)

**Flag 4 — two "mapped" counts exist and the page prints both.** The mapping-strength chip and
the denominators read `mapping_coverage_latest` (per posting: 25 mapped of 623 for skills in the
current artefact), while the Mapping quality table reads `mapping_quality_latest` (per outcome:
46 `mapped` skill outcomes). The two are different published quantities and already coexist on
the live page. The chip deliberately binds to `mapping_coverage_latest` so it can never
contradict the denominator sentence beside it — but the implementer should expect the
mapping-quality table to show the other number, and should not "fix" the chip to match it.

**Deliberately not changed:** tab machinery and script; filter form; CSV download; all generated
insight copy; all definition/caveat prose; the within-source relative-volume bar; suppression
copy; section order and slugs; `docs/index.html` (the committed artefact is untouched by this
design pass).

---

## 7. Guidelines review

Run with the `web-design-guidelines` skill: rules fetched fresh from
`raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md` on 2026-09-04,
applied to `design/prototype/index.html` (post-fix state, 70 KB) and to this specification.
Verification was structural: rendered in Chromium at 1280×900 and 390×844 with zero horizontal
overflow at both widths, computed styles checked for fonts, lamps, focus, and strip geometry,
and the heading ladder machine-checked (`[1, 2, 3, …]`, no skips, one `h1`).

### Findings and resolutions

| # | Finding (file:line) | Resolution |
| --- | --- | --- |
| 1 | `design/prototype/index.html:439,510,548,604` — scope plates rendered their names as styled `span`s, so Occupations and Requirements skipped from `h2` to `h4` (guideline: headings hierarchical; would also fail `release_check`'s no-skip rule) | **Fixed.** All eight scope plate/card names are now `<h3 class="scope-name" translate="no">` (`:212,242,348,400,439,510,548,604`); CSS `margin: 0` keeps the visual identical (`:94`); §3.1 now specifies the plate name as an `h3` by rule. |
| 2 | `design/prototype/index.html:6` (and `docs/index.html`, live page) — no `<meta name="theme-color">` matching the page ground (guideline: Dark Mode & Theming) | **Fixed** in the prototype (`content="#f4f6f5"`); §5.2 requires it; flagged for the implementation increment to add to `publish.py`'s head. |
| 3 | `design/prototype/index.html:212` — scope identifiers such as `jobtech-f5cf1d409aa51fad` are code tokens that auto-translation can garble (guideline: Locale & i18n — wrap code tokens with `translate="no"`) | **Fixed.** `translate="no"` on all eight scope names; §5.2 requires it on scope ids and on the source-code columns of requirement and provenance tables. |
| 4 | `docs/index.html:104` (live page) — the amber `:focus-visible` outline is 1.82:1 against white panels, below the 3:1 focus-appearance floor | **Designed out.** The spec's focus indicator is amber with an adjacent ink ring (amber vs ink 9.15:1; ring vs panel 16.67:1 — §5.2); prototype rule at `design/prototype/index.html:41`. The implementation increment must carry this fix. |
| 5 | `design/prototype/index.html:79` — lamp text such as `67 h old` could wrap between numeral and unit (guideline: non-breaking spaces in number/unit pairs) | **Harmless by construction:** the chip is `white-space: nowrap`, so the pair cannot split; prose spells units out (`67 hours old`). |
| 6 | `design/prototype/index.html:61` — `touch-action: manipulation` present on the mode links but the guideline applies to all tap targets | **Spec'd:** §5.2 requires `touch-action: manipulation` on tabs, buttons, and filter controls; the prototype has no buttons or form controls to carry it. |

### Consciously accepted

- **Server-rendered dates and numbers (no `Intl.*`).** The page is single-locale by architecture;
  formatting happens in Python at build time and there is no client-side formatting to migrate.
- **SVGs without explicit `height` attributes.** Frame strips carry `viewBox` + `width` +
  `height: auto`, which fixes the aspect ratio; the width/height rule targets `<img>` CLS, and
  no `<img>` exists on the page.
- **`color-scheme: light` with no dark theme.** The observatory page is deliberately light-only;
  the design system's contrast floor (§5.1) is computed against the light tokens.
- **No animation.** Nothing to virtualize, autoplay, or pause; the reduced-motion rule
  (`design/prototype/index.html:187`) remains as a guard for future transitions only.

Rules checked and passing without findings: semantic HTML, skip link, `scroll-margin-top`
(`:66`), `:focus-visible` over `:focus` (`:41`), no `outline-none`/`transition: all`, tabular
numerals (Data Register throughout, `:139`), `text-wrap: balance` on headings (`:54,67`),
long-content handling (`overflow-wrap: anywhere` on scope names; wrap cells on wide tables),
empty states (absence plates), `role="img"` + `aria-label`/`<title>`/`<desc>` on all figures,
decorative marks `aria-hidden`, `overscroll-behavior: contain` on scroll regions (`:135`),
hover states on links, ellipsis/curly-quote typography, `user-scalable` untouched, no external
assets or layout-reading script.

### Screenshots (evidence)

Captured from the prototype in `.playwright-mcp/`: `design-prototype-overview-desktop.png`
(first screenful, 1280×900 — both lamps and both strips visible), 
`design-prototype-occupations-desktop.png` (mapping chips and absence plates),
`design-prototype-full-desktop.png` (full page), and `design-prototype-mobile.png` (390×844 —
board stacked, coarse strip ladder active). Because the prototype ships no script, every
screenshot is simultaneously evidence of the no-JS rendering promised in §4.

---

## 8. Definition-of-done audit

Against the plan's §7, item by item:

| Requirement | Status | Where |
| --- | --- | --- |
| A competent implementer could build without asking what a state should say | Done | §3 specifies every state's copy verbatim; §6 gives emission notes. |
| Every §2 constraint addressed explicitly | Done | §5.4 maps each release rule; §1.5/§3.6/§3.7 hold the denominator, no-ratio, and scope-separation laws; §2.3 keeps slugs. |
| Five empty German tables have typed, differentiated states with copy | Done | §3.9 (occupation, skill, employment type, working hours, duration). |
| Region breadth has a visual form needing no external asset | Done | §1.5, §3.4. |
| Freshness/cadence legible in first screenful, not colour-alone | Done | §2.3 board, §3.2 lamps (word + age + threshold). |
| No element implies a cross-scope total; hero does not invite one | Done | §1.8 item 1, §2.3 (board replaces "Largest single observation"). |
| Guidelines review run, findings resolved or consciously accepted | Done | §7. |
| Self-critique names ≥1 default rejected for this brief | Done | §1.8 items 1, 4, 6 name template/dashboard/serif defaults rejected. |

One deliberate omission, recorded rather than hidden: the plan's §5 deliverable list asks for
"the one signature element" — §1.5 names it (the region-frame strip) and §1.6 supplies the mark
vocabulary that makes it legible; the two are one system, specified together. The plan also asks
the palette "state the reason" for keeping green — §1.2 gives it (identity retention plus the
annunciator-semantics upgrade as the real change).
