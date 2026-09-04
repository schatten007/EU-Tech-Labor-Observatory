# Source Feasibility Decision

Review date: 2026-08-15

> **Amendment, 2026-09-04 (appended; the 2026-08-15 review below is superseded where stated,
> never rewritten).** The project owner relaxed the ToS/robots gate on 2026-08-23 for this
> private research/educational project (recorded in the sister scraper lab's
> `SCRAPER_FEASIBILITY.md` "Germany programme" section). Under that owner decision, BA Jobsuche
> is an active collection lane (`scrapers/ba_jobsuche.py` in the sister lab), and this
> observatory publishes the result. The German data is a **stratified region-bounded sample
> with a capped within-stratum draw over a frozen 400-region NUTS-3 panel** — not a census, and
> not a partial crawl. The Approval Gate For Germany below is **unmet**: BA has not documented
> posting-level read access or republication permission, and the relaxation is the owner's
> decision recorded as such, not an approval by the source. Robots and ToS evidence stays
> recorded in the candidate rows below as evidence; it no longer blocks the lane.

## Decision

JobTech JobSearch is approved for the current Swedish technology-posting slice. No
reviewed German posting-level source is approved, so the project must not collect or
publish German posting observations yet. Germany-Sweden coverage remains blocked until a
documented access agreement permits complete posting-level collection and aggregate
republication.

## Candidate Review

| Source | Access and reuse evidence | Completeness | Decision |
| --- | --- | --- | --- |
| JobTech JobSearch, Sweden | Official public API and CC0 dataset: <https://data.jobtechdev.se/dataservice/jobsearch/> | Query-complete pagination is implemented; provider-default ordering is not a transactional snapshot | Approved for the fixed Swedish scope |
| BA Jobsuche, Germany | BA portal terms prohibit robots and reading interfaces for data collection/analysis: <https://www.arbeitsagentur.de/nutzungsbedingungen> | No BA-published public read API, stable pagination contract, or complete-sweep guarantee | **Active lane (owner-relaxed gate, 2026-08-23; superseded 2026-09-04).** Originally `Rejected` under the 2026-08-15 review. Collected by the sister lab via `scrapers/ba_jobsuche.py` as a stratified region-bounded sample with a capped within-stratum draw over a frozen 400-region NUTS-3 panel; published here as the `ba/de-nuts3-panel` scope |
| HR-BA-XML, Germany | Requires a BA cooperation agreement and client certificate; documented purpose is transferring a participant's own offers into BA: <https://www.arbeitsagentur.de/unternehmen/arbeitskraefte/hr-ba-xml-schnittstelle> | No documented nationwide vacancy read feed or snapshot semantics | Exploratory only |
| EURES vacancies, Germany | The public vacancy service does not establish supported non-partner API extraction and republication for this project: <https://europa.eu/eures/portal/jv-se/home?lang=en&pageCode=find_a_job> | No official public versioning, rate-limit, or complete-sweep contract was found | Rejected unless formal partner access is granted |
| BA statistics API, Germany | Official aggregate API: <https://statistik.arbeitsagentur.de/DE/Statischer-Content/Service/API/API-STEA.html> | Returns aggregate tables, not stable posting-level observations | Rejected as a posting source; suitable only as a future benchmark |

## Fixed Release Scope

- Source: JobTech JobSearch current Platsbanken advertisements.
- Country: Sweden (`SE`). Missing or non-Swedish country values are rejected.
- Technology definition: the canonical keyword query `q=utvecklare`.
- Sweep meaning: all pages for one fixed query scope, not all Swedish vacancies.
- Freshness threshold: 48 hours from `observed_at`, evaluated against an explicit reference
  timestamp.
- Collection period: begins when live Iteration 7 manifests are produced; the committed
  sample remains synthetic and is not release evidence.

Added 2026-09-04 under the owner-relaxed gate (see the amendment above):

- Source: BA Jobsuche current advertisements, collected by the sister scraper lab.
- Country: Germany (`DE`), through the `ba/de-nuts3-panel` scope.
- Sampling design: a stratified region-bounded sample with a capped within-stratum draw over
  a frozen 400-region NUTS-3 panel. It is not a census and not a partial crawl.
- Sweep meaning: one complete pass over the frozen panel, so a sweep is complete when every
  panel stratum has been drawn, not when every German posting has been seen.
- Stated limitation: the panel's own `coverage_limitations` string, read from the sweep
  manifest rather than restated here, so the page and the manifest cannot drift.
- Occupation field (added 2026-09-04, the basis for cancelling Increment 23): the BA search
  page carries no structured occupation field — only a free-text title — so the collector sets
  `occupation_mapping_status=not_present` by design (`scrapers/ba_jobsuche.py:51-52`,
  `scrapers/ba_jobsuche.py:1222-1246`) and no occupation aggregate is published for `DE`. Job
  titles and free text are never classified, so no title-like field may be added to the
  sanitize allowlist (`scripts/sanitize.py:31-35`) to manufacture one.

## Duplicate Policy

Counts are posting observations per source and scope. If the same real-world vacancy later
appears in more than one approved source, it is counted once in each source and is not
presented as a deduplicated unique total. Cross-source entity resolution is deferred until
it has an evaluated method.

## Approval Gate For Germany

A German source may be implemented only after its official owner documents all of the
following: posting-level read access, authentication and operational limits, stable record
identity, complete traversal or snapshot semantics, permission to retain observations and
publish derived aggregates, and source/licence attribution requirements. Successful calls
to undocumented portal endpoints do not satisfy this gate.

**Standing, and unmet (2026-09-04).** BA Jobsuche publishes German rows without meeting this
gate. That is only possible because the project owner relaxed the ToS/robots gate for this
private research/educational use on 2026-08-23; the relaxation is the owner's decision,
recorded as such in the amendment above and in the sister lab's feasibility record. It is not
an approval, an endorsement, or a documented access agreement from BA, and nothing on the
published page may claim that it is.
