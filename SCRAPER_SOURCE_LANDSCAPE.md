# Scraper Source Landscape (EU)

Survey of public job-vacancy sources in Germany and major EU countries for the
scrapers lab. Purpose: **identify candidate sources and rate the complexity of
building and running a crawler against each, plus the volume of data each would
yield.** This is a landscape scan only — no planning, no implementation.

Research date: 2026-08-21. Facts below come from provider documentation, open
data catalogues, and third-party crawler experience. **Nothing here replaces the
per-target checklist in `SCRAPER_FEASIBILITY.md`** (robots.txt, ToS, Crawl-Delay,
SAFE_FIELDS coverage must be verified live per target before implementation).

## How to read this document

Each source is scored on four axes:

| Axis | Meaning |
| --- | --- |
| **Build complexity** | How hard to write a working collector: API quality, pagination, auth, parsing |
| **Run complexity** | How hard to operate over time: rate limits, anti-bot, ToS friction, schema drift |
| **Data volume** | Amount of postings the source yields (active stock and/or per-sweep rows) |
| **Legal/ToS** | The charter's feasibility gate: `allowed` / `restricted` / `prohibited` / `grey` (undocumented) |

Complexity scale: **Low / Medium / High**. Volume scale: **S** < 5k, **M** 5–50k,
**L** 50–300k, **XL** 300k+ active postings. All sources are public PES/state
portals or EU-wide hubs unless marked; commercial boards (StepStone, Indeed,
LinkedIn) are excluded — their ToS prohibit automated access and their
anti-bot makes them a non-starter for this lab.

## Summary table

| # | Source | Country | Access | Auth | Build | Run | Volume | ToS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | BA Jobsuche API | DE | JSON REST (community-documented) | static key header | Low | Medium | XL (~1.9M) | **Prohibited** |
| 2 | Interamt | DE (public sector) | No public read API; Wicket HTML + browser | none | High | High | M (~90k/yr, ~12k live) | grey |
| 3 | Meinestadt.de | DE (regional) | HTML; Akamai Bot Manager | none | High | High | M (per-city caps) | **Prohibited** |
| 4 | EURES portal API | EU-wide | JSON REST (reverse-engineered) | none (sessionId) | Medium | Medium | **XL (~1.8M)** | grey |
| 5 | Arbetsförmedlingen JobTech | SE | JSON REST (official open data) | none | Low | Low | L (~100k+ active) | allowed |
| 6 | Työmarkkinatori | FI | REST + NDJSON (official) | API key (apply) | Low | Medium | M | allowed (agreement) |
| 7 | NAV stillings-feed | NO | JSON feed API (official) | JWT (apply) | Low | Medium | L (~1k/day new) | allowed (agreement) |
| 8 | Jobnet | DK | SOAP/webservice (B2B only) | formal agreement | High | High | M | **restricted** |
| 9 | UWV werk.nl / Open Match | NL | Aggregates (CSV) + HTML portal | none | Medium | Medium | L (~273k) | grey |
| 10 | France Travail API | FR | JSON REST (official) | API key (apply) | Low | Medium | XL (9.3M/yr) | allowed (agreement) |
| 11 | VDAB | BE (Flanders) | Public HTML landing pages (API v4 exists but is partnership-gated) | none for HTML; contract for API | Low-Med | Low | L (~233k) | HTML allowed (disclaimer); **API restricted (contract)** |
| 12 | AMS alle jobs / Open Data | AT | Aggregates (CSV) + HTML portal | none | Medium | Medium | M | grey (open data OK) |
| 13 | SEPE / Empléate | ES | HTML portal (JS) | none | Medium | Medium | S–M | grey |
| 14 | ANPAL / Cliclavoro | IT | HTML portal; no open offers API | login | High | High | S–M | grey |
| 15 | CBOP (ePraca) | PL | JSON REST + SOAP (official) | none / web service | Low | Low | **L (nationwide)** | allowed (public) |
| 16 | IEFP iefponline | PT | HTML portal | none | Medium | Medium | S (~4k) | grey |
| 17 | JobsIreland | IE | HTML portal | none | Medium | Medium | S–M (~13k) | grey |
| 18 | Úřad práce / MPSV | CZ | JSON/JSON-LD + SPARQL (open data) | none | Low | Low | M–L | allowed (open data) |
| 19 | Baltic PES (LV/LT/EE) | LV/LT/EE | open-data datasets / HTML | mixed | Medium | Medium | S–M | mostly open data |
| 20 | Adzuna | DE + 18 others | JSON REST (official public API) | API key (free signup) | Low | Medium | L (100k+/DE) | allowed (API ToS) |
| 21 | Kimeta.de | DE | HTML search engine (no public API) | none | Medium | Medium | **XL (~1.5–1.8M)** | grey |
| 22 | Joblift | DE + FR/UK/NL/BE | HTML aggregator (no public API) | none | Medium | Medium | L | grey |
| 23 | Arbeitnow | DE/UK (tech, remote) | JSON REST (official, no key) | none | Low | Low | S–M (tech only) | allowed |
| 24 | Stellenanzeigen.de | DE | HTML + JSON-LD JobPosting | none | Medium | Medium | M (~10k+ active) | grey |
| 25 | StepStone | DE/AT/CH | HTML (Akamai Bot Manager) | none | High | High | L–XL | **Prohibited** |
| 26 | Indeed | DE/EU | HTML (Cloudflare + JS) | none | High | High | XL | **Prohibited** |

Details for each source below.

---

## Germany

### 1. Bundesagentur für Arbeit — Jobsuche (jobboerse.arbeitsagentur.de)

The largest job database in Germany (~**1.9M open positions**, ~350k
apprenticeships). This is the crown jewel for German coverage.

- **Access:** JSON REST at `rest.arbeitsagentur.de/jobboerse/jobsuche-service`.
  Community-documented (bundesAPI/jobsuche-api, OpenAPI at jobsuche.api.bund.dev).
  Endpoints: `pc/v6/jobs` (search), `pc/v4/jobdetails/{base64(refnr)}` (detail).
  Auth is a fixed header `X-API-Key: jobboerse-jobsuche` (a client id, not a
  personal credential).
- **Build complexity:** Low. Clean JSON, pagination via `page`/`size`, filters
  (`was`, `wo`, `berufsfeld`, `angebotsart`, `arbeitszeit`, `befristung`).
  Detail call per refnr (base64).
- **Run complexity:** Medium. Undocumented rate limits; listings are volatile
  (expire). No official SLA. The endpoint is stable in practice but there is no
  support channel.
- **Data volume:** **XL** (~1.9M stock). Full national coverage, all occupations.
- **ToS:** **Prohibited.** BA's Nutzungsbedingungen explicitly forbid robots/web
  spiders and using the API "contrary to the intended purpose" for data
  collection/evaluation. Data is not open data; BA publicly objected (2021) to
  the API being openly documented. This is the exact target the main project
  rejected. **Blocked by the charter's feasibility gate** unless a data/API
  agreement is obtained — same conclusion as the main project's
  `SOURCE_FEASIBILITY.md`.

### 2. Interamt (interamt.de)

The central portal for German **public sector** jobs (federal, states,
municipalities): ~**90,000 postings/yr**, ~**12,000 live**. Very high signal for
tech/data/IT public roles; negligible duplication with private boards.

- **Access:** No public read API. The portal is Apache **Wicket** (stateful
  Java): HTTP-only approaches fail with redirect loops and server-side session
  handling; the practical path is a real browser session (Playwright), with
  "load more" pagination in-page. There is an employer-facing
  `gate.interamt.de` REST API (OpenAPI, sandbox) but it is for submitting
  vacancies, not reading them.
- **Build complexity:** High (browser automation + Wicket session handling).
- **Run complexity:** High (browser maintenance, session fragility, no rate
  guarantee; needs a headless browser).
- **Data volume:** **M** (~90k/yr, ~12k live). Pure public sector.
- **ToS:** grey — not explicitly scraping-hostile in what was reviewed, but no
  robots/Crawl-Delay evidence collected yet. Must be verified before build.
- **Note:** a third-party scanner (santifer/career-ops scan-interamt.mjs) exists
  and confirms the Playwright-only reality.

### 3. Meinestadt.de (jobs.meinestadt.de)

Network of German city portals with a job section per city. Regional depth that
the BA and Interamt do not provide.

- **Access:** HTML only. Runs behind **Akamai Bot Manager** — TLS-fingerprint
  blocking; datacenter proxies get connection resets, residential DE proxies
  required. Hard cap of **1,000 results per query** (page 51 returns 404).
- **Build complexity:** High (anti-bot, per-city URL scheme).
- **Run complexity:** High (Akamai evasion, proxy rotation, per-query caps mean
  multi-query harvesting).
- **Data volume:** **M** (e.g. ~15.6k live in Berlin alone; national total not
  published).
- **ToS:** **Prohibited** — the AGB explicitly bans scraping/automated collection
  of content for any purpose other than the intended one. **Blocked by the
  feasibility gate.**

### 3a. Adzuna (adzuna.de — DE domain of the EU/global aggregator)

Aggregator with an **official, free public REST API** (developer.adzuna.com) —
the cleanest sanctioned path to broad German listings without BA access.
Covers DE plus 18 other country domains (AT, BE, CH, ES, FR, GB, IE, IT, NL, PL
among them), so one collector codebase reaches many of the countries this lab
cares about.

- **Access:** `api.adzuna.com/v1/api/jobs/de/search/{page}` with free
  `app_id`/`app_key` from developer signup. Structured JSON, filters (keyword,
  location, salary, contract type, hours, date-posted), categories endpoint,
  plus salary/vacancy trend endpoints.
- **Build complexity:** Low (documented REST, paginated, stable schema).
- **Run complexity:** Medium (rate limits on the free tier; aggregator data
  quality varies by source board; salary/`Jobsworth` fields are estimates).
- **Data volume:** **L** (100k+ live DE listings typical of the domain; all
  occupations).
- **ToS:** allowed under the API terms (official key, research use is a listed
  purpose). **Strong German fallback to BA Jobsuche.**

### 3b. Kimeta.de

Germany's leading job **search engine / aggregator** ("die Jobsuchmaschine"):
~**1.5M–1.8M listings** (02/2025 stat), covering the large boards plus company
career sites and 75+ regional portals. The best raw DE volume after the BA.

- **Access:** No public read API. HTML search with filters (location, radius,
  contract, employment type); per-city and per-keyword pages. Third-party
  scrapers exist (Apify actor with 400+ German city expansion).
- **Build complexity:** Medium (HTML parsing, per-city expansion, dedupe).
- **Run complexity:** Medium (pagination, de-duplication across sources, no
  stable machine-readable contract).
- **Data volume:** **XL** (~1.5–1.8M aggregated listings).
- **ToS:** grey. kimeta's terms are business/consumer-oriented; no explicit
  scraping ban was found, but copyright on compiled listings is asserted.
  Needs a live robots.txt + ToS check before build.

### 3c. Joblift (joblift.de; also .fr / .co.uk / .nl / .be)

EU-wide job aggregator (Hamburg-based) that pulls postings from employer
career sites and partner boards across **5 European markets**.

- **Access:** No public read API. HTML search pages; a few third-party
  scrapers/templates exist.
- **Build complexity:** Medium (HTML, pagination, per-market domains).
- **Run complexity:** Medium (cross-market domains, dedupe, no API contract).
- **Data volume:** **L** (aggregated; strongest in DACH + FR/UK/NL/BE).
- **ToS:** grey (consumer AGB; no explicit scraping clause seen — verify).

### 3d. Arbeitnow (arbeitnow.com)

Berlin-based tech/startup job board with an **official, keyless public JSON
API** — the easiest possible integration in the whole landscape.

- **Access:** `arbeitnow.com/api/job-board-api` (no key, documented via
  Postman). Fields incl. title, company, location, `remote`, tags, date. Filters
  like `visa_sponsorship`, `remote`. Data sourced from ATS feeds (accurate,
  direct from employers). UK twin at arbeitnow.co.uk.
- **Build complexity:** Low. **Run complexity:** Low.
- **Data volume:** **S–M** (thousands live; **tech/startup only**, mostly remote
  and DACH) — a niche, not a national source.
- **ToS:** allowed (public API, no key). Great quick win for a tech slice.

### 3e. Stellenanzeigen.de

One of Germany's **Top 3 job portals**, ~**10k+ active postings** across all
industries, server-rendered with **JSON-LD `JobPosting`** markup on detail
pages.

- **Access:** HTTP GET on search/detail pages; JSON-LD gives structured
  data. Cloudflare protection reported — a datacenter proxy/`got-scraping`
  (TLS-fingerprinting) client is needed; no browser required.
- **Build complexity:** Medium (HTML + JSON-LD extraction, proxy handling).
- **Run complexity:** Medium (Cloudflare changes, promoted-listing ordering).
- **Data volume:** **M** (~10k+ active).
- **ToS:** grey (no explicit clause found in research; verify live).

### 3f. StepStone (stepstone.de)

Germany's largest commercial board (DACH-wide). Research shows it is one of the
most aggressively defended European job sites: **Akamai Bot Manager** with
TLS-fingerprint (JA3/JA4) checks, HTTP/2 frame-order validation, JS challenge,
IP reputation — and ToS **prohibits** scraping.

- **Build complexity:** High. **Run complexity:** High (constant Akamai churn).
- **Volume:** **L–XL**. **ToS:** **Prohibited.** **Blocked by the feasibility
  gate** — requires residential proxies and anti-bot evasion, which the charter
  forbids.

### 3g. Indeed (indeed.de)

The largest global aggregator. ToS explicitly bans bots/scrapers, and Indeed
has **pursued legal action against scrapers**; Cloudflare + JS challenges make
it High/High complexity.

- **Volume:** **XL**. **ToS:** **Prohibited.** **Blocked.** (Indeed's own
  Publisher API is paused since 2022 for new publishers.)

---

## EU-wide

### 4. EURES portal API (europa.eu/eures)

The European Employment Services hub — **all 31 EURES states feed their PES
vacancies in**. Largest single EU pool: search API reports **~1.8M active
vacancies** (`numberRecords` example 1,787,657).

- **Access:** JSON REST at `europa.eu/eures/api/jv-searchengine/...`,
  **reverse-engineered** (rorar/EURES-API-Documentation, 20 endpoints, OpenAPI
  3.1). Search is a POST with filters incl. `locationCodes` (country codes like
  `de`), `occupationUris`/`skillUris` (**ESCO URIs natively**), pagination up to
  `resultsPerPage=50`. A `sessionId` string is required but can be self-assigned.
  Detail endpoint returns full structured vacancy. Statistics endpoints give
  per-country/per-sector/per-occupation counts.
- **Build complexity:** Medium (reverse-engineered contract; response schema
  documented but unofficial).
- **Run complexity:** Medium. EURES availability is a dependency on the
  Commission's portal; per-country quality varies because each PES feeds its own
  subset. ESCO URIs are a huge win for the `occupation_mapping` fields.
- **Data volume:** **XL** (~1.8M, EU-wide, by country).
- **ToS:** grey. Public portal; data is provided by member states for search and
  matching. Anonymized data may be stored and released "for research and
  statistical purposes" (Commission Decision 2017/1257). But the API itself is
  undocumented/reverse-engineered — need a live robots/ToS check and probably a
  data-access arrangement with EURES for systematic collection.

---

## Nordic

### 5. Arbetsförmedlingen JobTech (SE) — already the main project's source

Official open data. `jobsearch.api.jobtechdev.se` (search), `jobstream` (new/updated
ads), `historical.api.jobtechdev.se` (full history). No auth, generous rate
limits, taxonomy API for occupations/skills. Already implemented in the main
checkout.

- **Build:** Low. **Run:** Low. **Volume:** **L** (~100k+ active ads).
- **ToS:** allowed (open data, free use). The established baseline for this lab.

### 6. Työmarkkinatori / Job Market Finland (FI)

Official job-postings API (REST + **NDJSON streaming**, ESCO occupations/skills,
structured `openPositions`, timestamps, multi-language).

- **Access:** "Retrieval interface" v2.0, REST, requires **accepting terms of
  use + an activation form to the KEHA Centre** to get credentials (API key,
  Kipa integration platform). NDJSON output, filters, pagination.
- **Build:** Low (clean OpenAPI + NDJSON).
- **Run:** Medium (manual onboarding; credentials; ESCO codesets).
- **Volume:** **M** (~tens of thousands active).
- **ToS:** allowed under agreement (explicit terms-of-use process).

### 7. NAV stillings-feed (NO)

Official feed of **all** job ads registered with NAV since ~2019 (the law
requires employers to report vacancies to NAV; FINN.no ads are excluded).
Feed semantics: paginated pages with `next_url`, **~1,000 ads published per
day**, ads never active >6 months, `ACTIVE`/`INACTIVE` status per ad.

- **Access:** `pam-stilling-feed.nav.no/api/v1/feed`, JWT auth (a public token
  exists for experimentation; production token requires registering as a
  consumer — free). `If-Modified-Since`/`ETag` supported.
- **Build:** Low (feed API, well documented).
- **Run:** Medium (continuous polling design, JWT rotation, ACTIVE/INACTIVE
  reconciliation on consumer side).
- **Volume:** **L** (~1k/day new; steady stock).
- **ToS:** allowed under agreement (open data licence; terms of use must be
  accepted).

**Measured live 2026-08-22/23 (Increment 6 — implemented):** robots.txt is
**absent** (404) on the feed host; unauthenticated requests answer 401 with no
`WWW-Authenticate`. Pages hold **exactly 1,000 items**, `next_id` equals the
page ETag, and end-of-feed is `next_url`/`next_id` both null. The event stream
runs at **~3,000–6,000 events/day** (1,000 items span 4–8 h of business time,
far less at night) and folds at about **2 events per ad**. The ToS
(`arbeidsplassen.nav.no/vilkar-api`) names *"statistiske/analytiske formål"* as
an independent permitted purpose, so this is **allowed outright, not merely
under agreement**. Revalidation needs `If-None-Match` **alone** (adding
`If-Modified-Since` re-seeks and returns 200). Detail payloads carry
`categoryList` with **ESCO occupation URIs** alongside JANZZ and STYRK08 —
the first source in this lab that populates `esco_occupation_uri` directly —
but INACTIVE details are usually content-masked (measured: 2 of 20 still
carried `ad_content`). One operational caveat: the host was briefly **degraded**
during the build (26–28 s token responses, a 500, read timeouts) and recovered
after a five-minute back-off, so a generous timeout and a cached token matter
more than a tight one.

### 8. Jobnet / STAR (DK)

Denmark's national job portal. **No public read/search API.** The
JobannonceService webservice is B2B only: requires a formal
integration/testing process with STAR (contact spoc@star.dk), a signed
tilslutningsaftale (connection agreement), and test-environment sign-off. A
consumer RSS feed for saved searches existed but was discontinued.

- **Build:** High (SOAP webservice, agreement process, test env).
- **Run:** High (contract-dependent, low volume for this effort).
- **Volume:** **M** (Danish stock).
- **ToS:** **restricted** (formal agreement required for any access). Low
  priority unless a Denmark angle is wanted.

---

## Western / Central Europe

### 9. UWV werk.nl / Open Match Data (NL)

Dutch PES. **Open Match Data** (CC-BY 4.0) provides **aggregated** vacancy
counts by occupation and 4-digit postcode area — great for macro stats, **no
posting-level records**. The live search portal werk.nl lists **~273k
vacancies**; the underlying Jobfeed is TextKernel's proprietary crawl (not
public). Note: since Dec 2025 UWV changed vacancy-data supplier, time series
were restated.

- **Build:** Medium (either consume aggregate CSV/API, or scrape werk.nl HTML for
  posting level).
- **Run:** Medium (monthly cadence for aggregates; portal scraping unknown
  stability).
- **Volume:** **L** (~273k active) but posting-level access unclear.
- **ToS:** grey for portal scraping; aggregates are open (CC-BY 4.0). Verify
  werk.nl robots before scraping.

### 10. France Travail — API Offres d'emploi (FR)

Official, real-time API of active offers collected by France Travail (formerly
Pôle emploi). **~9.3M offers published over the last 12 months** nationally.

- **Access:** REST JSON, paginated, filters by métier/département/contrat, plus
  referential endpoints (lieux, secteurs, contrats, formations, métiers).
  Requires **signing a licence contract** to get API credentials (free, but a
  contract).
- **Build:** Low (well-documented official API).
- **Run:** Medium (contract onboarding; real-time, so frequent sweeps).
- **Volume:** **XL** (9.3M/yr flow; very large active stock).
- **ToS:** allowed under agreement (open data law; contact data consent-gated).

### 11. VDAB (BE — Flanders)

Flemish PES. Two surfaces, opposite verdicts (verified live 2026-08-22, see
`SCRAPER_FEASIBILITY.md` Increment 5):

**(a) Vacature API v4** — developer portal `developer.vdab.be/opendata`,
`GET /vacatures`, JSON, `X-IBM-Client-Id` header, structured fields incl.
`jobdomein` (C2 occupation codes), postcode, region. **Correction to the
earlier note that this is a "free app registration":** VDAB's own extranet
documentation requires *"een partnership … en na het ondertekenen van een
samenwerkingsovereenkomst"* — an approved partnership plus a signed cooperation
agreement, professional use only, with a VDAB-side added-value test. **ToS:
restricted (contract).** Not implementable as a scraper; only as an
access-request task.

**(b) Public job-search website** — `www.vdab.be/vindeenjob/jobs/<slug>`,
server-rendered SEO landing pages with 28 vacancy tiles each (title, employer,
contract type, `Online sinds` date, deep link), discovered via the six sitemaps
advertised in `robots.txt` (34,903 landing pages; 214 weekly vacancy sitemaps
with ids + `lastmod`). **~232,944 active vacancies** advertised on the search
page. No in-page pagination (`?limit`/`?page`/`?start` ignored). The Angular
app's internal JSON API `/api/vindeenjob/` is **robots-disallowed** and off-limits
(also 403 in practice). **ToS: allowed** — the vdab.be disclaimer states *"Je mag
informatie op onze website kopiëren, afdrukken en gebruiken voor informatieve
doeleinden"*, with the VDAB name/logo protected as trademarks.

- **Build:** Low-Med (HTML tiles, breadth-based coverage). **Run:** Low.
  **Volume:** **L** (~233k advertised; Flanders only — Wallonia and Brussels are
  separate PES: Le Forem, Actiris, no open API found).
- Region is resolvable to NUTS 3 2024 through Basisregisters Vlaanderen, whose
  `postinfo/{postcode}` payload returns `nuts3` directly (`9000` → `BE234`).
  Built 2026-08-22: **529 postcodes listed → 528 mapped, 0 unmatched against
  Eurostat GISCO NUTS 2024, all 22 Flemish arrondissements covered**.
- **Implemented as Increment 5 (DONE 2026-08-22):** `scrapers/vdab.py`. A live
  500-page breadth sweep yielded **12,282 rows with region `mapped` on 100%** and
  zero 4xx, i.e. **5.3% of the advertised stock** — the 28-tiles-per-page ceiling
  is the binding constraint, not the request budget.

### 12. AMS — alle jobs / Open Data (AT)

Austrian PES. Two layers: (a) **Open Data aggregates** on data.gv.at
(offene Stellen nach ÖNACE/region, CSV, monthly, "uneingeschränkte
Weiterverwendung" licence); (b) the **"alle jobs"** search engine — an
aggregator mixing AMS vacancies, eJob-Room, a crawler of Austrian company
sites, plus BA (DE) and Italian South Tyrol/Trento feeds.

- **Build:** Medium (either consume open-data CSVs for aggregates, or scrape
  "alle jobs" for posting level — the crawler-mixed source list needs care).
- **Run:** Medium.
- **Volume:** **M** (Austrian stock; note the BA-DE content overlaps source #1).
- **ToS:** open data for aggregates; portal scraping grey. Reasonable source if
  Austria matters.

---

## Southern / Eastern Europe

### 13. SEPE / Empléate (ES)

Spanish PES. Open-data catalogue has **aggregates only** (contracts, registered
unemployment, job seekers by municipality). The **Empléate** portal is a JS SPA
with offer search; no official offers API. Third-party scrapers exist but were
deprecated/flaky (e.g. Canarias-only).

- **Build:** Medium (SPA scraping + reverse-engineering, or aggregate-only).
- **Run:** Medium. **Volume:** **S–M** (active offers, several thousand).
- **ToS:** grey; open data for aggregates, portal scraping unverified. Low value
  vs. complexity compared with France/Poland/Germany.

### 14. ANPAL / Cliclavoro (IT)

Italian PES. The DOL (Domanda e Offerta) service sits behind **MyANPAL login**
(SPID/CIE); Cliclavoro offers a public offer search but no documented open
offers API; Ministry open data has datasets but not a clean vacancy feed.

- **Build:** High (login-gated portal, no clean API).
- **Run:** High. **Volume:** **S–M**.
- **ToS:** grey. Low priority; most Italian posting-level data effectively
  requires scraping or agreements.

### 15. CBOP / ePraca (PL)

Poland's **Centralna Baza Ofert Pracy** — national PES vacancy base, fed by all
powiat/województwo labour offices plus OHP and accredited agencies. Official
**WebService** (SOAP + a JSON REST integration) downloads **all active offers**
as zipped JSON batches (1,000/package, 174 fields: occupation, location,
salary, contract type, dates, employer metadata). Also exposed via the portal's
own JSON search API that requires no login and is reported to have **no anti-bot
and no geo-lock**.

- **Build:** Low (both SOAP and JSON paths documented; Python reader exists —
  OJALAB/CBOP-datasets).
- **Run:** Low (batch download; no pagination gymnastics).
- **Volume:** **L** (nationwide Polish stock, ~tens of thousands active).
- **ToS:** allowed (public portal; integration webservice is the sanctioned
  path). Strong, easy first target after the German ones.
- **Status:** **DONE 2026-08-21** (Increment 1). The portal search JSON API was
  verified live and is what the collector uses:
  `POST https://oferty.praca.gov.pl/portal-api/v3/oferta/wyszukiwanie` with body
  `{"kodJezyka":"PL"}` — no auth, Spring Data pagination, **22,068 active
  proposals** at 100/page at sweep time. The SOAP integrator service requires a
  ministry-registered Partner id, so it is not used. See `SCRAPER_FEASIBILITY.md`
  and `SESSIONS.md`.

### 16. IEFP iefponline (PT)

Portuguese PES portal. Public offer search (search.do forms) with ~**4.2k live
offers**; no documented API.

- **Build:** Medium (HTML form scraping). **Run:** Medium. **Volume:** **S**.
- **ToS:** grey. Low payoff for the effort.

### 17. JobsIreland (IE)

Irish PES portal. ~**13k active opportunities**, HTML search with rich facets
(sector, career level, vacancy type), no public API.

- **Build:** Medium (HTML + pagination). **Run:** Medium. **Volume:** **S–M**.
- **ToS:** grey. Moderate value if Ireland is in scope.

### 18. Úřad práce / MPSV (CZ)

Czech PES open data. National catalogue (data.gov.cz / data.mpsv.cz) publishes
**"Volná místa za celou ČR"** — the full list of vacancies registered by the
labour office, as **JSON / JSON-LD / SPARQL**, updated daily, with a documented
shape. Clean open-data contract.

- **Build:** Low. **Run:** Low (daily refresh). **Volume:** **M–L** (Czech stock).
- **ToS:** allowed (national open data catalogue). Very easy target for a CEE
  slice.

### 19. Baltic states (LV / LT / EE)

- **Latvia (NVA):** open-data portal data.gov.lv publishes the **"Vakances"**
  dataset (daily refresh, API available) plus monthly aggregates. S–M volume.
  ToS: allowed (open data).
- **Lithuania (Užimtumo tarnyba):** open data on data.gov.lt, aggregates and
  vacancy data published via the state portal; posting-level access not cleanly
  documented. S–M volume. ToS: open data, but verify granularity.
- **Estonia (Töötukassa):** statistics are published monthly (Excel) via the
  state open-data portal; **no public posting-level API** found. S volume. ToS:
  open data but aggregate-only.

---

## Data volume ranking (posting-level)

| Tier | Sources |
| --- | --- |
| **XL (300k+)** | BA Jobsuche (1.9M), EURES (1.8M), France Travail (9.3M/yr), Kimeta (~1.5–1.8M), Indeed (blocked) |
| **L (50–300k)** | JobTech SE, NAV NO, UWV NL (273k), CBOP PL, Adzuna DE (100k+), VDAB BE (~233k), StepStone (blocked), Joblift |
| **M (5–50k)** | Interamt (~90k/yr), Meinestadt, Työmarkkinatori FI, Jobnet DK, AMS AT, MPSV CZ, Stellenanzeigen.de (~10k+) |
| **S (<5k)** | IEFP PT, JobsIreland IE, SEPE ES active, ANPAL IT, Baltic PES, Arbeitnow (tech/remote niche) |

## Targetable countries — shortlist

Ordered by (build + run complexity) vs (volume + access certainty). This is the
priority ranking for choosing the lab's first scrapers.

| Priority | Country | Why | Access path |
| --- | --- | --- | --- |
| 1 | **Poland** | National PES coverage, sanctioned batch API, no anti-bot, L volume | CBOP/ePraca JSON + SOAP |
| 2 | **Sweden** | Already live in the main project; reference implementation | JobTech API |
| 3 | **France** | XL volume, official API; one licence acceptance (click-through, not a signed contract) | France Travail API Offres d'emploi |
| 4 | **Czechia** | Open-data JSON, daily, documented; easy | MPSV data.gov.cz |
| 5 | **Belgium (Flanders)** | L volume on a robots-permitted public site; the API needs a partnership contract | VDAB public job-search HTML (not the API) |
| 6 | **Norway** | Feed API, ~1k new/day; consumer registration | NAV stillings-feed |
| 7 | **Finland** | ESCO-native NDJSON; onboarding is a form | Työmarkkinatori |
| 8 | **Germany** | Highest value, hardest access — see below | Adzuna (best sanctioned), else Kimeta/Joblift/Stellenanzeigen, else BA agreement |
| 9 | **Latvia / Lithuania** | Open-data daily refreshes, cheap | NVA / Užimtumo tarnyba |
| 10 | **Netherlands** | Aggregates only without portal scraping | UWV Open Match Data |

**Germany without BA Jobsuche** — ordered by feasibility:

1. **Adzuna DE** — official public API, free key, L volume, multi-country.
2. **Kimeta** — largest aggregator volume (~1.5–1.8M), HTML; ToS grey.
3. **Stellenanzeigen.de** — ~10k+ active, JSON-LD structured, HTTP-only.
4. **Joblift** — aggregator, 5 EU markets; HTML.
5. **Arbeitnow** — keyless API but tech/remote niche only.
6. **StepStone / Indeed / Meinestadt** — **blocked** (ToS + anti-bot).
7. **BA Jobsuche** — still the most complete German dataset; requires a data
   agreement (HR-BA-XML partner access or an explicit BA arrangement) rather
   than scraping. If a German national slice is a hard requirement, an access
   request is the legitimate route.

## Feasibility quick read

- **Cleanest builds (Low/Low, sanctioned access):** JobTech SE (done), CBOP PL,
  MPSV CZ, France Travail FR (licence acceptance), NAV NO (apply), Työmarkkinatori
  FI (apply), Arbeitnow (keyless), **Adzuna** (free key, covers DE). These are
  the lab's natural first targets.
- **Sanctioned but only via the public website:** VDAB BE — its Vacature API
  needs an approved partnership + signed agreement, while the public
  job-search HTML is robots-permitted and covered by a disclaimer that allows
  informational re-use (canary passed 2026-08-22).
- **High value but legally blocked or grey:** BA Jobsuche (largest DE source,
  ToS-prohibited — would need a BA agreement), EURES (~1.8M but undocumented
  API + needs a data arrangement), Meinestadt (Akamai + ToS-ban), StepStone
  (Akamai + ToS-ban), Indeed (Cloudflare + ToS-ban + litigation history).
- **Public-sector niche:** Interamt (Playwright-only, high run cost, small but
  unique public-sector data).
- **Aggregate-only or login-walled, low priority:** UWV posting-level (scrape
  needed), SEPE, ANPAL, Jobnet, IEFP, Baltic EE.

Next step when a target is chosen: fill the corresponding row in
`SCRAPER_FEASIBILITY.md` (robots.txt fetch, ToS clause, Crawl-Delay, SAFE_FIELDS
coverage, PII risk, rate limits, snapshot semantics) before any code is written.
