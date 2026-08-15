# Source Feasibility Decision

Review date: 2026-08-15

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
| BA Jobsuche, Germany | BA portal terms prohibit robots and reading interfaces for data collection/analysis: <https://www.arbeitsagentur.de/nutzungsbedingungen> | No BA-published public read API, stable pagination contract, or complete-sweep guarantee | Rejected |
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
