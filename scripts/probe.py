"""Phase 0 one-shot probe: record fixtures (step 6) and measure EURES volume (step 8).

Network access ONLY under --live. Everything else in this repo runs offline against
tests/fixtures/. See AGENTS.md.

    uv run python scripts/probe.py --live     # record fixtures + measure (network)
    uv run python scripts/probe.py --sample   # rebuild sample parquet (offline)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SAMPLE = ROOT / "data" / "sample" / "postings_sample.parquet"

EURES = "https://europa.eu/eures/api/jv-searchengine/public"
JOBTECH = "https://jobsearch.api.jobtechdev.se"
JOBTECH_HIST = "https://historical.api.jobtechdev.se"
ESCO = "https://ec.europa.eu/esco/api"

UA = "eu-tech-labour-observatory/0.1 (non-commercial research; +see repo README)"

# ISCO-08 groups defining "tech" scope for this project:
#   C25  ICT professionals          C35  ICT technicians
#   C133 ICT service managers
# Group-level URIs are accepted by the occupationUris filter (verified 2026-08-12),
# so three URIs cover all ICT occupations without enumerating leaves.
ICT_URIS = [f"http://data.europa.eu/esco/isco/{c}" for c in ("C25", "C35", "C133")]

# ponytail: fixed 0.5s between requests instead of adaptive backoff. EURES has no
# published rate limit; raise this (or add backoff) if a sweep ever sees 429/401.
PAUSE_S = 0.5


def _req(url: str, payload: dict[str, Any] | None = None) -> Any:
    headers = {"User-Agent": UA, "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    with urlopen(Request(url, data=data, headers=headers), timeout=90) as r:
        body: Any = json.loads(r.read().decode("utf-8"))
    time.sleep(PAUSE_S)
    return body


def eures_search(
    rpp: int = 1,
    occupations: list[str] | None = None,
    countries: list[str] | None = None,
) -> dict[str, Any]:
    """POST /jv-search/search. All fields are required by the API even when empty."""
    payload: dict[str, Any] = {
        "resultsPerPage": rpp,
        "page": 1,
        "sortSearch": "BEST_MATCH",
        "keywords": [],
        "publicationPeriod": None,
        "occupationUris": occupations or [],
        "skillUris": [],
        "requiredExperienceCodes": [],
        "positionScheduleCodes": [],
        "sectorCodes": [],
        "educationAndQualificationLevelCodes": [],
        "positionOfferingCodes": [],
        "locationCodes": countries or [],
        "euresFlagCodes": [],
        "otherBenefitsCodes": [],
        "requiredLanguages": [],
        "sessionId": "",
        "requestLanguage": "en",
    }
    out: dict[str, Any] = _req(f"{EURES}/jv-search/search", payload)
    return out


def _write(name: str, obj: Any) -> None:
    path = FIXTURES / name
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}  ({path.stat().st_size / 1024:.0f} KiB)")


def record() -> None:
    """Step 6: record the fixtures that are both the test basis and the quota firewall."""
    print("recording fixtures")
    _write("eures_search.json", eures_search(rpp=3, occupations=ICT_URIS))
    _write("jobtech_search.json", _req(f"{JOBTECH}/search?q=utvecklare&limit=2"))
    _write("jobtech_historical.json", _req(f"{JOBTECH_HIST}/search?q=utvecklare&limit=2"))
    _write(
        "esco_occupation.json",
        _req(f"{ESCO}/resource/occupation?uri=http://data.europa.eu/esco/isco/C2512&language=en"),
    )


def measure() -> None:
    """Step 8 + open items 1 and 2: measure instead of estimating."""
    print("\nmeasuring EURES")
    n_jobs = int(_req(f"{EURES}/statistics/getNumberOfJobs")["numberOfJobs"])
    stats: list[dict[str, Any]] = _req(f"{EURES}/statistics/getCountryStats")
    sum_jobs = sum(int(c["jobs"]) for c in stats)
    sum_posts = sum(int(c["posts"]) for c in stats)
    unfiltered = int(eures_search()["numberRecords"])
    ict = int(eures_search(occupations=ICT_URIS)["numberRecords"])

    print("\n### Open item 2 - getNumberOfJobs vs getCountryStats")
    print(f"| getNumberOfJobs | {n_jobs:,} |")
    print(f"| sum(getCountryStats.jobs) | {sum_jobs:,} |")
    print(f"| sum(getCountryStats.posts) | {sum_posts:,} |")
    print(f"| search numberRecords (unfiltered) | {unfiltered:,} |")
    print(f"-> numberRecords/sum(jobs) ratio {unfiltered / sum_jobs:.4f}")
    print(f"-> getNumberOfJobs/sum(posts) ratio {n_jobs / sum_posts:.4f}")

    print("\n### Open item 1 - measured ICT volume and sweep cost")
    print(f"ICT (C25+C35+C133) EU-wide: {ict:,}  ({100 * ict / unfiltered:.2f}% of all)")

    rows: list[tuple[str, int, int]] = []
    for c in sorted(stats, key=lambda c: -int(c["jobs"])):
        code = str(c["code"]).lower()
        n = int(eures_search(countries=[code], occupations=ICT_URIS)["numberRecords"])
        if n:
            rows.append((code, n, -(-n // 50)))  # ceil div: pages at rpp=50

    print("\n| country | ICT jobs | pages @rpp50 | over 10k cap |")
    print("|---|---|---|---|")
    for code, n, pages in rows:
        print(f"| {code} | {n:,} | {pages} | {'YES' if n > 10_000 else '-'} |")
    print(f"\ncountries with ICT jobs: {len(rows)}")
    print(f"sum of per-country ICT: {sum(n for _, n, _ in rows):,}")
    print(
        f"requests per full sweep: {sum(p for _, _, p in rows) + len(rows)} "
        f"(pages + 1 count request per country)"
    )
    print(
        f"partitions needing a finer split (>10k): "
        f"{[c for c, n, _ in rows if n > 10_000] or 'none'}"
    )


def build_sample() -> None:
    """Step 7: sample parquet so dbt and the dashboard build offline in any worktree.

    Shaped like RAW LANDING (source-native column names, nested structs intact) so
    stg_postings.sql does real mapping work rather than a passthrough. Built from the
    recorded Swedish fixture, so the shape is measured rather than invented.

    application_contacts is dropped here, not later: it carries PII and CC0 does not
    waive GDPR. So are employer.phone_number/email and application_details, which are
    the non-obvious PII carriers in this schema. This projection is an ALLOWLIST on
    purpose -- a SELECT * sample would publish contact data (plan R5).
    """
    import duckdb

    src = FIXTURES / "jobtech_search.json"
    SAMPLE.parent.mkdir(parents=True, exist_ok=True)
    duckdb.execute(
        """
        COPY (
          SELECT h.id,
                 h.headline,
                 h.webpage_url,
                 h.source_type,
                 h.description.text                        AS description_text,
                 h.employer.name                            AS employer_name,
                 h.employer.organization_number             AS employer_org_number,
                 h.workplace_address.country_code           AS country_code,
                 h.workplace_address.region_code            AS region_code,
                 h.workplace_address.municipality_code      AS municipality_code,
                 h.workplace_address.city                   AS city,
                 h.workplace_address.postcode               AS postcode,
                 h.occupation.concept_id                    AS occupation_concept_id,
                 h.occupation.label                         AS occupation_label,
                 h.occupation_group.concept_id              AS occupation_group_concept_id,
                 h.occupation_group.label                   AS occupation_group_label,
                 h.occupation_field.label                   AS occupation_field_label,
                 h.employment_type.label                    AS employment_type_label,
                 h.working_hours_type.label                 AS working_hours_type_label,
                 h.duration.label                           AS duration_label,
                 h.salary_type.label                        AS salary_type_label,
                 h.number_of_vacancies,
                 h.experience_required,
                 h.must_have,                -- authority answer key for extraction eval
                 h.nice_to_have,
                 h.publication_date,
                 h.last_publication_date,
                 h.application_deadline,
                 h.removed,
                 CAST(h.removed_date AS VARCHAR)            AS removed_date,
                 h.timestamp
          FROM read_json_auto($1) AS j, UNNEST(j.hits) AS t(h)
        ) TO $2 (FORMAT parquet, COMPRESSION zstd)
        """,
        [str(src), str(SAMPLE)],
    )
    row = duckdb.execute("SELECT count(*) FROM read_parquet($1)", [str(SAMPLE)]).fetchone()
    print(
        f"wrote {SAMPLE.relative_to(ROOT)} "
        f"({SAMPLE.stat().st_size} bytes, {row[0] if row else 0} rows)"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true", help="hit the network: record + measure")
    ap.add_argument("--sample", action="store_true", help="rebuild sample parquet (offline)")
    args = ap.parse_args()
    if not (args.live or args.sample):
        ap.print_help()
        return 2
    if args.live:
        record()
        measure()
    if args.sample:
        build_sample()
    return 0


if __name__ == "__main__":
    sys.exit(main())
