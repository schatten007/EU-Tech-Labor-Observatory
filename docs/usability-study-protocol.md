# Iteration 11 — Usability Study Protocol (prepared, unrun)

**Status:** prepared 2026-09-04 (Plan 1 Task 5). **Not recruited, not run, no results.**
The study is Iteration 11's last open item ("user validation pending"). Nothing in this
document was produced by observing a participant; every task below is a prediction of what
will be asked, written before any session happens so the tasks cannot be quietly reshaped
around what the page happens to answer well.

**Participants (to recruit, not yet recruited):** at least five students or recent graduates
(the roadmap's bar). Mixed study backgrounds if available; no prior exposure to this page.

**Material:** `docs/index.html` opened in a clean browser profile, no JavaScript required
(the page is server-rendered and release-checked for no-JS readability; enabling JS is a
participant choice, and whether they reach for it is itself an observation). A quiet room,
one participant at a time, think-aloud encouraged, moderator takes verbatim notes and does
not help. No time pressure announced; time-to-task recorded silently.

## Tasks

Each task is read aloud once, then answered from the page. "Where on the page did you look
first?" is asked after every task.

1. **German breadth.** "How many of Germany's ~400 regions does this data cover, and where
   do you see that?" — target: the breadth line "392 of 400 DE NUTS-3 regions have at least
   one mapped posting." in the DE regional block, with the sampling caveat under it.
   Failure mode worth recording: reading the top-25 region *table* as the coverage, or the
   headline 29,068 as a region count.

2. **The empty occupation ranking.** "What does it mean that Germany's occupation ranking is
   empty?" — target: the empty-by-construction sentence in the DE occupation block: the
   source carries no structured occupation field, so the ranking is empty by construction,
   not because there are no jobs. Failure mode: concluding "Germany has no job data" or
   "no IT jobs in Germany".

3. **Freshness.** "When was the data last updated, for each country?" — target: the Status
   section's demand table (observed-at per scope) and the freshness badges. Failure mode:
   trusting the page build time in the footer as the data time.

4. **Comparability (the real test).** "Sweden has 623 postings and Germany has 29,068. Can
   you compare the two countries' job markets with these numbers?" — target: **no**. The
   page states absolute counts are not comparable between countries and scopes: different
   sources, different scopes, one a keyword query and one a capped stratified sample.
   **If a participant compares them anyway, that is a design finding**, not a participant
   error: it belongs in the next design brief (Plan 2), not in a code patch made now.
   Record verbatim what they compared and which sentence they missed or dismissed.

5. **A removed posting (comprehension, from the older kit wording).** "What does it mean
   when the page counts a posting as closed?" — target: closures are inferred from absence
   at the next complete sweep (plus source-reported removals where the source states them);
   right-censoring is stated beside the survival figures. Failure mode: reading an inferred
   closure as a confirmed event.

## Recording

Per participant: one row per task — attempted / completed, first-look location, verbatim
misunderstanding if any, and any cross-country or postings-vs-vacancies confusion (the
roadmap's named risk areas: postings, vacancies, source coverage, country comparisons,
inferred removal). Aggregate only after the fifth participant; nothing feeds back into the
interface until the study is done and the findings are written up with the aggregate.

## Explicitly out of scope

- Recruiting, running, or writing up results (this plan only prepares).
- Any page change in response to imagined findings — the page is a published artefact with a
  release gate; revisions get their own increment after the study reports.
- Passing the comparability confusion off as user error — route it to Plan 2's brief.
