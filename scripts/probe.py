"""Phase 0 one-shot probe: record private responses and measure EURES volume.

Network access ONLY under --live. Everything else in this repo runs offline against
synthetic sample data.

    uv run python -m scripts.probe --live     # record private responses + measure (network)
    uv run python -m scripts.probe --sample   # rebuild sample observations (offline)
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
RAW_PROBES = ROOT / "data" / "raw" / "probe"
SAMPLE = ROOT / "data" / "sample" / "postings_sample.ndjson"

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
    RAW_PROBES.mkdir(parents=True, exist_ok=True)
    path = RAW_PROBES / name
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}  ({path.stat().st_size / 1024:.0f} KiB)")


def record() -> None:
    """Record private source responses outside git."""
    print("recording private responses")
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
    """Build synthetic observations with the collector's PII-free landing shape."""
    from scripts.collect import normalize_jobtech_hit
    from scripts.sanitize import sanitize_record

    SAMPLE.parent.mkdir(parents=True, exist_ok=True)
    observations: tuple[tuple[str, dict[str, Any]], ...] = (
        (
            "2026-08-05T09:00:00Z",
            {
                "id": "synthetic-001",
                "publication_date": "2026-08-01T08:00:00Z",
                "last_publication_date": "2026-08-02T09:00:00Z",
                "country_code": "SE",
                "number_of_vacancies": 1,
            },
        ),
        (
            "2026-08-05T09:00:00Z",
            {
                "id": "synthetic-002",
                "publication_date": "2026-08-03T08:00:00Z",
                "last_publication_date": "2026-08-04T09:00:00Z",
                "removed_date": "2026-08-10T10:00:00Z",
                "country_code": "SE",
                "number_of_vacancies": 1,
            },
        ),
        (
            "2026-08-05T09:00:00Z",
            {
                "id": "synthetic-003",
                "publication_date": "2026-08-04T08:00:00Z",
                "last_publication_date": "2026-08-04T09:00:00Z",
                "country_code": "SE",
                "number_of_vacancies": 1,
            },
        ),
        (
            "2026-08-06T09:00:00Z",
            {
                "id": "synthetic-001",
                "publication_date": "2026-08-01T08:00:00Z",
                "last_publication_date": "2026-08-02T09:00:00Z",
                "country_code": "SE",
                "number_of_vacancies": 1,
            },
        ),
    )
    key = b"offline-synthetic-sample-key-32b"
    rows = [
        sanitize_record(normalize_jobtech_hit(hit, observed_at), key)
        for observed_at, hit in observations
    ]
    SAMPLE.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    print(f"wrote {SAMPLE.relative_to(ROOT)} ({SAMPLE.stat().st_size} bytes, {len(rows)} rows)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true", help="hit the network: record + measure")
    ap.add_argument("--sample", action="store_true", help="rebuild sample observations (offline)")
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
