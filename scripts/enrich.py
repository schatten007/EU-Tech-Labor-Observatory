"""Deterministic, version-pinned enrichment before the privacy boundary."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ROOT = ROOT / "data" / "reference"
NUTS_VERSION = "NUTS-2024"
JOBTECH_TAXONOMY_VERSION = "30"
ESCO_VERSION = "1.2.1"
STATUSES = {"mapped", "ambiguous", "low_confidence", "unmapped", "not_present"}


@dataclass(frozen=True)
class MappingCandidate:
    uri: str
    label: str
    relation: str
    confidence: str


@dataclass(frozen=True)
class ReferenceTables:
    geography: dict[tuple[str, str], tuple[str, str]]
    occupations: dict[str, tuple[MappingCandidate, ...]]
    skills: dict[str, tuple[MappingCandidate, ...]]
    manual: dict[tuple[str, str], MappingCandidate]
    hashes: dict[str, str]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def _candidate(row: dict[str, str]) -> MappingCandidate:
    uri = row["target_uri"]
    if not uri.startswith("http://data.europa.eu/esco/"):
        raise ValueError(f"invalid ESCO URI: {uri}")
    return MappingCandidate(uri, row["target_label"], row["relation"], row["confidence"])


def _group(rows: list[dict[str, str]]) -> dict[str, tuple[MappingCandidate, ...]]:
    grouped: dict[str, list[MappingCandidate]] = {}
    for row in rows:
        grouped.setdefault(row["source_concept_id"], []).append(_candidate(row))
    return {key: tuple(value) for key, value in grouped.items()}


def load_references(root: Path = REFERENCE_ROOT) -> ReferenceTables:
    geography_path = root / "geography_nuts_2024.csv"
    occupation_path = root / "jobtech_occupation_esco_1.2.1.csv"
    skill_path = root / "jobtech_skill_esco_1.2.1.csv"
    review_path = root / "manual_reviews.csv"
    paths = (geography_path, occupation_path, skill_path, review_path)
    if not all(path.exists() for path in paths):
        missing = ", ".join(path.name for path in paths if not path.exists())
        raise ValueError(f"missing reference file(s): {missing}")

    geography: dict[tuple[str, str], tuple[str, str]] = {}
    for row in _rows(geography_path):
        key = (row["source_type"], row["source_code"])
        value = (row["nuts_code"], row["nuts_label"])
        if key in geography and geography[key] != value:
            raise ValueError(f"ambiguous geography reference: {key}")
        geography[key] = value

    occupations = _group(_rows(occupation_path))
    skills = _group(_rows(skill_path))
    manual: dict[tuple[str, str], MappingCandidate] = {}
    for row in _rows(review_path):
        key = (row["dimension"], row["source_concept_id"])
        if row["status"] != "mapped":
            continue
        candidate = _candidate(row)
        if key in manual and manual[key] != candidate:
            raise ValueError(f"conflicting manual review: {key}")
        manual[key] = candidate

    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    return ReferenceTables(geography, occupations, skills, manual, hashes)


def _mapping(
    dimension: str,
    source_id: str | None,
    candidates: dict[str, tuple[MappingCandidate, ...]],
    references: ReferenceTables,
) -> dict[str, Any]:
    if not source_id:
        return {
            "uri": None,
            "label": None,
            "status": "not_present",
            "confidence": None,
            "method": "source_absent",
            "source_language": "sv",
            "jobtech_taxonomy_version": JOBTECH_TAXONOMY_VERSION,
            "esco_version": ESCO_VERSION,
        }
    manual = references.manual.get((dimension, source_id))
    if manual is not None:
        return {
            "uri": manual.uri,
            "label": manual.label,
            "status": "mapped",
            "confidence": manual.confidence,
            "method": "manual_review",
            "relation": manual.relation,
            "source_language": "sv",
            "jobtech_taxonomy_version": JOBTECH_TAXONOMY_VERSION,
            "esco_version": ESCO_VERSION,
        }
    options = candidates.get(source_id, ())
    selected: MappingCandidate | None
    if len(options) == 0:
        status = "unmapped"
        selected = None
    elif len(options) > 1:
        status = "ambiguous"
        selected = None
    else:
        selected = options[0]
        status = "mapped" if selected.relation == "exact-match" else "low_confidence"
    return {
        "uri": selected.uri if selected and status == "mapped" else None,
        "label": selected.label if selected and status == "mapped" else None,
        "status": status,
        "confidence": selected.confidence if selected else None,
        "method": "crosswalk" if selected else "no_match",
        "relation": selected.relation if selected else None,
        "source_language": "sv",
        "jobtech_taxonomy_version": JOBTECH_TAXONOMY_VERSION,
        "esco_version": ESCO_VERSION,
    }


def enrich_hit(hit: dict[str, Any], references: ReferenceTables | None = None) -> dict[str, Any]:
    refs = references or load_references()
    address = hit.get("workplace_address")
    address = address if isinstance(address, dict) else {}
    municipality = address.get("municipality_code")
    region = address.get("region_code")
    nuts = refs.geography.get(("municipality", str(municipality))) if municipality else None
    method = "municipality_crosswalk" if nuts else None
    if nuts is None and municipality and len(str(municipality)) >= 2:
        # A Swedish kommunkod's first two digits are its länskod (region code).
        nuts = refs.geography.get(("region", str(municipality)[:2]))
        method = "municipality_prefix_crosswalk" if nuts else None
    if nuts is None and region:
        nuts = refs.geography.get(("region", str(region)))
        method = "region_crosswalk" if nuts else None
    region_result = {
        "nuts_code": nuts[0] if nuts else None,
        "nuts_label": nuts[1] if nuts else None,
        "status": (
            "mapped" if nuts else "not_present" if not (municipality or region) else "unmapped"
        ),
        "method": method or ("source_absent" if not (municipality or region) else "no_match"),
        "nuts_version": NUTS_VERSION,
    }
    occupation = hit.get("occupation")
    occupation_id = occupation.get("concept_id") if isinstance(occupation, dict) else None
    occupation_result = _mapping("occupation", occupation_id, refs.occupations, refs)
    skill_ids: set[str] = set()
    for field in ("must_have", "nice_to_have"):
        requirements = hit.get(field)
        if not isinstance(requirements, dict):
            continue
        skills = requirements.get("skills")
        if not isinstance(skills, list):
            continue
        for skill in skills:
            if isinstance(skill, dict) and isinstance(skill.get("concept_id"), str):
                skill_ids.add(skill["concept_id"])
    skill_results = [
        _mapping("skill", skill_id, refs.skills, refs) for skill_id in sorted(skill_ids)
    ]
    if not skill_results:
        skill_results = [_mapping("skill", None, refs.skills, refs)]
    return {"region": region_result, "occupation": occupation_result, "skills": skill_results}


def reference_provenance(references: ReferenceTables | None = None) -> dict[str, str]:
    refs = references or load_references()
    return {
        "nuts_version": NUTS_VERSION,
        "jobtech_taxonomy_version": JOBTECH_TAXONOMY_VERSION,
        "esco_version": ESCO_VERSION,
        "reference_hashes": ";".join(f"{key}={refs.hashes[key]}" for key in sorted(refs.hashes)),
    }
