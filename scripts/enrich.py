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
# What a reviewer is allowed to record. `low_confidence` is excluded because it describes a
# candidate, and a refusing row names none; `not_present` is excluded because it would deny
# source data that demonstrably exists. Anything else is a typo and must not pass silently.
MANUAL_STATUSES = {"mapped", "ambiguous", "unmapped"}


@dataclass(frozen=True)
class MappingCandidate:
    uri: str
    label: str
    relation: str
    confidence: str


@dataclass(frozen=True)
class ManualReview:
    """A reviewed decision: either a confirmed mapping, or a refusal that names no target.

    Refusal exists because a redirect cannot express every review outcome. The crosswalk
    sometimes states one ESCO concept to be the exact equivalent of two different source
    concepts, and for the losing one there is often no correct URI anywhere in the reference to
    redirect to -- so a reviewer able only to redirect can merely trade one wrong mapping for
    another. A refusal instead restores the outcome the rule produced before it was widened, for
    that one audited concept, and leaves the rule untouched everywhere else.
    """

    status: str
    candidate: MappingCandidate | None


@dataclass(frozen=True)
class ReferenceTables:
    geography: dict[tuple[str, str], tuple[str, str]]
    occupations: dict[str, tuple[MappingCandidate, ...]]
    skills: dict[str, tuple[MappingCandidate, ...]]
    manual: dict[tuple[str, str], ManualReview]
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
    manual: dict[tuple[str, str], ManualReview] = {}
    for row in _rows(review_path):
        key = (row["dimension"], row["source_concept_id"])
        status = row["status"]
        # Previously any non-mapped row was skipped, which silently discarded the one review
        # outcome that cannot be expressed as a redirect. A status this loader does not
        # understand is now an error, because a dropped review reads exactly like no review.
        if status not in MANUAL_STATUSES:
            raise ValueError(f"unsupported manual review status for {key}: {status!r}")
        review: ManualReview
        if status == "mapped":
            review = ManualReview(status, _candidate(row))
        else:
            named = tuple(
                field
                for field in ("target_uri", "target_label", "relation", "confidence")
                if row[field]
            )
            if named:
                raise ValueError(f"refusing manual review for {key} must not name {named}")
            review = ManualReview(status, None)
        if key in manual and manual[key] != review:
            raise ValueError(f"conflicting manual review: {key}")
        manual[key] = review

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
        # A review wins over the crosswalk in both directions. A human looked at this concept
        # and the reference did not, so a refusal is evidence just as much as a redirect is.
        if manual.candidate is None:
            return {
                "uri": None,
                "label": None,
                "status": manual.status,
                "confidence": None,
                "method": "manual_review",
                "relation": None,
                "source_language": "sv",
                "jobtech_taxonomy_version": JOBTECH_TAXONOMY_VERSION,
                "esco_version": ESCO_VERSION,
            }
        return {
            "uri": manual.candidate.uri,
            "label": manual.candidate.label,
            "status": "mapped",
            "confidence": manual.candidate.confidence,
            "method": "manual_review",
            "relation": manual.candidate.relation,
            "source_language": "sv",
            "jobtech_taxonomy_version": JOBTECH_TAXONOMY_VERSION,
            "esco_version": ESCO_VERSION,
        }
    options = candidates.get(source_id, ())
    selected: MappingCandidate | None
    method = "no_match"
    if len(options) == 0:
        status = "unmapped"
        selected = None
    elif len(options) > 1:
        # A concept with several candidates is normally refused, because picking one of two
        # close-matches would be a guess dressed up as a mapping. One sole exact-match is not a
        # guess: the crosswalk states an equivalence, and the rest are looser relations that lose
        # to it on their own terms. Two exact matches are a genuine conflict and stay refused.
        # The method is recorded separately from plain crosswalk so every such decision can be
        # audited later; this is a provenance rule, not a measured accuracy gain.
        exact = [option for option in options if option.relation == "exact-match"]
        if len(exact) == 1:
            selected = exact[0]
            status = "mapped"
            method = "exact_match_tiebreak"
        else:
            status = "ambiguous"
            selected = None
    else:
        selected = options[0]
        status = "mapped" if selected.relation == "exact-match" else "low_confidence"
        method = "crosswalk"
    return {
        "uri": selected.uri if selected and status == "mapped" else None,
        "label": selected.label if selected and status == "mapped" else None,
        "status": status,
        "confidence": selected.confidence if selected else None,
        "method": method,
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
