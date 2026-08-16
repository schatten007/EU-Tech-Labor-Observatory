"""Evaluate pinned occupation and skill mappings against a privacy-safe review sample."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.enrich import ESCO_VERSION, JOBTECH_TAXONOMY_VERSION, ReferenceTables, enrich_hit

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample" / "mapping_review_sample.ndjson"
REPORT = ROOT / "data" / "sample" / "mapping_quality_report.json"
EVALUATION_BASIS = (
    "Regression check that the deterministic mapper reproduces the official "
    "JobTech->ESCO crosswalk on a reviewed developer-scope sample. It is not an "
    "independent accuracy audit; that requires manually labelled live job ads."
)


def _metric(tp: int, fp: int, fn: int) -> dict[str, int | float | None]:
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def evaluate(sample: Path = SAMPLE, references: ReferenceTables | None = None) -> dict[str, Any]:
    occupation_tp = occupation_fp = occupation_fn = 0
    skill_tp = skill_fp = skill_fn = 0
    sample_size = 0
    review_dates: set[str] = set()
    with sample.open(encoding="utf-8") as rows:
        for line in rows:
            if not line.strip():
                continue
            row = json.loads(line)
            sample_size += 1
            review_dates.add(str(row["reviewed_at"]))
            hit = {
                "occupation": {"concept_id": row["occupation_concept_id"]},
                "must_have": {
                    "skills": [
                        {"concept_id": concept_id} for concept_id in row["skill_concept_ids"]
                    ]
                },
            }
            result = enrich_hit(hit, references)
            predicted_occupation = result["occupation"]["uri"]
            expected_occupation = row["expected_occupation_uri"]
            occupation_tp += int(
                predicted_occupation is not None and predicted_occupation == expected_occupation
            )
            occupation_fp += int(
                predicted_occupation is not None and predicted_occupation != expected_occupation
            )
            occupation_fn += int(
                expected_occupation is not None and predicted_occupation != expected_occupation
            )
            predicted_skills = {skill["uri"] for skill in result["skills"] if skill["uri"]}
            expected_skills = set(row["expected_skill_uris"])
            skill_tp += len(predicted_skills & expected_skills)
            skill_fp += len(predicted_skills - expected_skills)
            skill_fn += len(expected_skills - predicted_skills)
    return {
        "sample_size": sample_size,
        "review_date": max(review_dates) if review_dates else None,
        "jobtech_taxonomy_version": JOBTECH_TAXONOMY_VERSION,
        "esco_version": ESCO_VERSION,
        "evaluation_basis": EVALUATION_BASIS,
        "occupation": _metric(occupation_tp, occupation_fp, occupation_fn),
        "skill": _metric(skill_tp, skill_fp, skill_fn),
    }


def main() -> int:
    report = evaluate()
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {REPORT.relative_to(ROOT)} ({report['sample_size']} reviewed postings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
