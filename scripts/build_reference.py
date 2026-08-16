"""Opt-in network build of pinned reference crosswalks. NOT part of make check.

Fetches Sweden geography and JobTech->ESCO occupation/skill mappings from the pinned
JobTech Taxonomy version and writes deterministic CSVs plus a provenance manifest.
Run manually with `make reference`; it is never a prerequisite of an offline target.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from scripts.enrich import ESCO_VERSION, JOBTECH_TAXONOMY_VERSION, NUTS_VERSION

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ROOT = ROOT / "data" / "reference"
GRAPHQL = "https://taxonomy.api.jobtechdev.se/v1/taxonomy/graphql"
SWEDEN_CONCEPT_ID = "i46j_HmG_v64"
VERSION = int(JOBTECH_TAXONOMY_VERSION)  # Single source of truth: scripts/enrich.py.
USER_AGENT = "eu-tech-labour-observatory/0.3 (non-commercial research; +see repo README)"
RELATIONS = ("exact_match", "close_match", "broad_match", "narrow_match")

GEOGRAPHY_QUERY = (
    f'{{ concepts(id:"{SWEDEN_CONCEPT_ID}", version:{VERSION}){{'
    ' narrower(type:"region"){ national_nuts_level_3_code_2019 nuts_level_3_code_2021'
    " preferred_label } } }"
)


def _mapping_query(source_type: str, target_type: str) -> str:
    matches = " ".join(
        f'{relation}(type:"{target_type}"){{ esco_uri preferred_label }}' for relation in RELATIONS
    )
    return (
        f'{{ concepts(type:"{source_type}", version:{VERSION}){{ id preferred_label {matches} }} }}'
    )


def _get(query: str) -> dict[str, Any]:
    request = Request(
        f"{GRAPHQL}?query={quote(query)}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urlopen(request, timeout=180) as response:
        payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(f"taxonomy query failed: {payload['errors']}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("taxonomy response missing data")
    return data


def _geography_rows() -> list[dict[str, str]]:
    concepts = _get(GEOGRAPHY_QUERY)["concepts"]
    regions = concepts[0]["narrower"] if concepts else []
    rows: list[dict[str, str]] = []
    for region in regions:
        code = region.get("national_nuts_level_3_code_2019")
        nuts = region.get("nuts_level_3_code_2021")
        if not code or not nuts:
            continue
        rows.append(
            {
                "source_type": "region",
                "source_code": code,
                "nuts_code": nuts,
                "nuts_label": region.get("preferred_label", ""),
            }
        )
    return rows


def _mapping_rows(source_type: str, target_type: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for concept in _get(_mapping_query(source_type, target_type))["concepts"]:
        for relation in RELATIONS:
            for esco in concept.get(relation) or []:
                uri = esco.get("esco_uri")
                if not uri:
                    continue
                rows.append(
                    {
                        "source_concept_id": concept["id"],
                        "source_label": concept.get("preferred_label", ""),
                        "target_uri": uri,
                        "target_label": esco.get("preferred_label", ""),
                        "relation": relation.replace("_", "-"),
                        "confidence": "high" if relation == "exact_match" else "low",
                    }
                )
    return rows


def _write_csv(
    path: Path, fieldnames: list[str], rows: list[dict[str, str]], sort: list[str]
) -> None:
    # retrieved_at is deliberately NOT written into the row bodies: reference_hashes is a
    # SHA-256 over these files, so a volatile timestamp would make identical-version rebuilds
    # non-reproducible and desync committed manifests. Retrieval time lives in the manifest.
    columns = [*fieldnames, "source_url", "source_version"]
    ordered = sorted(rows, key=lambda row: tuple(row[key] for key in sort))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in ordered:
            writer.writerow({**row, "source_url": GRAPHQL, "source_version": str(VERSION)})


def main() -> int:
    REFERENCE_ROOT.mkdir(parents=True, exist_ok=True)
    geography = _geography_rows()
    _write_csv(
        REFERENCE_ROOT / "geography_nuts_2024.csv",
        ["source_type", "source_code", "nuts_code", "nuts_label"],
        geography,
        ["source_type", "source_code"],
    )
    occupations = _mapping_rows("occupation-name", "esco-occupation")
    _write_csv(
        REFERENCE_ROOT / "jobtech_occupation_esco_1.2.1.csv",
        [
            "source_concept_id",
            "source_label",
            "target_uri",
            "target_label",
            "relation",
            "confidence",
        ],
        occupations,
        ["source_concept_id", "target_uri"],
    )
    skills = _mapping_rows("skill", "esco-skill")
    _write_csv(
        REFERENCE_ROOT / "jobtech_skill_esco_1.2.1.csv",
        [
            "source_concept_id",
            "source_label",
            "target_uri",
            "target_label",
            "relation",
            "confidence",
        ],
        skills,
        ["source_concept_id", "target_uri"],
    )
    manifest = {
        "jobtech_taxonomy_version": str(VERSION),
        "esco_version": ESCO_VERSION,
        "nuts_version": NUTS_VERSION,
        "source_url": GRAPHQL,
        "retrieved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "row_counts": {
            "geography_nuts_2024.csv": len(geography),
            "jobtech_occupation_esco_1.2.1.csv": len(occupations),
            "jobtech_skill_esco_1.2.1.csv": len(skills),
        },
        "hashes": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(REFERENCE_ROOT.glob("*.csv"))
        },
    }
    (REFERENCE_ROOT / "reference_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "wrote reference tables: "
        f"{len(geography)} regions, {len(occupations)} occupation mappings, "
        f"{len(skills)} skill mappings"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
