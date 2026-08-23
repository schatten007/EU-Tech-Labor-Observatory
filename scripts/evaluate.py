"""Evaluate pinned occupation and skill mappings against a privacy-safe review sample.

Two things are scored here that the earlier version could not see.

A *refusal* is an outcome, not a gap. A row that names an occupation concept and expects no URI
asserts that the mapper ought to decline, so declining is a true negative and mapping anyway is a
false positive. That is kept strictly apart from a row that names no occupation concept at all,
which does not test the occupation side and is skipped there: crediting the mapper for declining
something nobody asked about is the hole this module used to have. Refusals are counted on the
occupation side only, because that is where the sample carries a row-level expectation able to
express one; the skill side compares URI sets and has no place to say "expect nothing for this
concept".

An *inexact* match is reported twice rather than resolved once. Every audited row carries the
verdict a reviewer reached on the crosswalk's chosen target, and a `narrower-or-broader` verdict is
scored strictly (a false positive: not the equivalence the crosswalk asserts) and leniently (a true
positive: the best target the reference contains). Both readings are published side by side.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.enrich import (
    ESCO_VERSION,
    JOBTECH_TAXONOMY_VERSION,
    MappingCandidate,
    ReferenceTables,
    enrich_hit,
    load_references,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample" / "mapping_review_sample.ndjson"
REPORT = ROOT / "data" / "sample" / "mapping_quality_report.json"
VERDICTS = frozenset({"same", "narrower-or-broader", "wrong"})
VERDICT_SOURCES = frozenset({"13a-recorded", "13b-rejudged", "crosswalk-regression", "fixture"})
EVALUATION_BASIS = (
    "Regression check that the deterministic mapper reproduces the official "
    "JobTech->ESCO crosswalk on a reviewed developer-scope sample, together with the "
    "reviewed audit of every concept the exact-match tiebreak decides in the published "
    "sweep. It is not an independent accuracy audit; that requires manually labelled live "
    "job ads."
)
INEXACT_BASIS = (
    "A concept judged narrower-or-broader is scored twice: strictly as a false positive, "
    "because the chosen target is not the equivalence the crosswalk asserts, and leniently "
    "as a true positive, because it is the best target ESCO 1.2.1 contains. The rule was "
    "recorded before these figures were computed, and neither reading alone is the accuracy "
    "of the mapper."
)
COLLISION_BASIS = (
    "Diagnostic, enforced nowhere: how many concepts the tiebreak decides share their chosen "
    "URI with another source concept that the crosswalk also calls an exact match. Requiring "
    "sole claimancy was measured and rejected, because it refuses more correct mappings than "
    "wrong ones."
)


def _metric(tp: int, fp: int, fn: int) -> dict[str, int | float | None]:
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


@dataclass
class _Tally:
    """One side of the mapping, counted under both readings of an inexact match.

    `precision` and `recall` keep their textbook formulas in both readings. True negatives are
    counted and reported beside them, never folded into either: a metric whose name no longer
    matches its formula is worse than a missing metric.
    """

    strict_tp: int = 0
    strict_fp: int = 0
    strict_fn: int = 0
    lenient_tp: int = 0
    lenient_fp: int = 0
    lenient_fn: int = 0

    def credit(self, count: int, *, inexact: bool) -> None:
        """Score a prediction that matched its expectation."""
        self.lenient_tp += count
        if inexact:
            # Same treatment an expected refusal gets when the mapper maps anyway: the mapping
            # should not have been asserted, so precision pays and recall is untouched.
            self.strict_fp += count
        else:
            self.strict_tp += count

    def miss(self, *, fp: int = 0, fn: int = 0) -> None:
        """Score an outcome both readings agree is wrong."""
        self.strict_fp += fp
        self.lenient_fp += fp
        self.strict_fn += fn
        self.lenient_fn += fn

    def readings(self) -> dict[str, dict[str, int | float | None]]:
        return {
            "strict": _metric(self.strict_tp, self.strict_fp, self.strict_fn),
            "lenient": _metric(self.lenient_tp, self.lenient_fp, self.lenient_fn),
        }


def _rows(sample: Path) -> Iterator[dict[str, Any]]:
    with sample.open(encoding="utf-8") as lines:
        for line in lines:
            if line.strip():
                yield json.loads(line)


def _sole_exact(options: tuple[MappingCandidate, ...]) -> MappingCandidate | None:
    """The candidate the tiebreak picks, or None when the rule does not decide this concept."""
    if len(options) <= 1:
        return None
    exact = [option for option in options if option.relation == "exact-match"]
    return exact[0] if len(exact) == 1 else None


def _collision_census(
    table: dict[str, tuple[MappingCandidate, ...]], audited: set[str]
) -> dict[str, int]:
    claimants: dict[str, set[str]] = {}
    for source_id, options in table.items():
        for option in options:
            if option.relation == "exact-match":
                claimants.setdefault(option.uri, set()).add(source_id)
    tiebroken = 0
    with_rival = 0
    in_sample = 0
    for source_id, options in table.items():
        chosen = _sole_exact(options)
        if chosen is None:
            continue
        tiebroken += 1
        if claimants.get(chosen.uri, set()) - {source_id}:
            with_rival += 1
            in_sample += int(source_id in audited)
    return {
        "tiebroken_concepts": tiebroken,
        "with_rival_exact_match": with_rival,
        "in_review_sample": in_sample,
    }


def evaluate(sample: Path = SAMPLE, references: ReferenceTables | None = None) -> dict[str, Any]:
    refs = references or load_references()
    occupation = _Tally()
    skill = _Tally()
    true_negatives = 0
    correct_refusals = 0
    incorrect_refusals = 0
    occupation_inexact = 0
    skill_inexact = 0
    verdicts: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    audited: dict[str, set[str]] = {"occupation": set(), "skill": set()}
    sample_size = 0
    review_dates: set[str] = set()

    for row in _rows(sample):
        sample_size += 1
        review_dates.add(str(row["reviewed_at"]))
        verdict = row["verdict"]
        if verdict is not None and verdict not in VERDICTS:
            raise ValueError(f"unknown mapping verdict: {verdict!r}")
        if row["verdict_source"] not in VERDICT_SOURCES:
            raise ValueError(f"unknown verdict source: {row['verdict_source']!r}")
        verdicts[verdict or "unjudged"] += 1
        sources[str(row["verdict_source"])] += 1
        inexact = verdict == "narrower-or-broader"

        occupation_id = row["occupation_concept_id"]
        hit = {
            "occupation": {"concept_id": occupation_id},
            "must_have": {
                "skills": [{"concept_id": concept_id} for concept_id in row["skill_concept_ids"]]
            },
        }
        result = enrich_hit(hit, refs)

        # A row without an occupation concept does not test the occupation side. Only a row that
        # names one is scored there, and then an expected null means the mapper should refuse.
        if occupation_id is not None:
            audited["occupation"].add(str(occupation_id))
            occupation_inexact += int(inexact)
            predicted = result["occupation"]["uri"]
            expected = row["expected_occupation_uri"]
            if expected is None:
                if predicted is None:
                    true_negatives += 1
                    correct_refusals += 1
                else:
                    occupation.miss(fp=1)
            elif predicted is None:
                incorrect_refusals += 1
                occupation.miss(fn=1)
            elif predicted == expected:
                occupation.credit(1, inexact=inexact)
            else:
                occupation.miss(fp=1, fn=1)

        if row["skill_concept_ids"]:
            audited["skill"].update(str(concept_id) for concept_id in row["skill_concept_ids"])
            skill_inexact += int(inexact)
        predicted_skills = {mapping["uri"] for mapping in result["skills"] if mapping["uri"]}
        expected_skills = set(row["expected_skill_uris"])
        skill.credit(len(predicted_skills & expected_skills), inexact=inexact)
        skill.miss(
            fp=len(predicted_skills - expected_skills),
            fn=len(expected_skills - predicted_skills),
        )

    return {
        "sample_size": sample_size,
        "review_date": max(review_dates) if review_dates else None,
        "jobtech_taxonomy_version": JOBTECH_TAXONOMY_VERSION,
        "esco_version": ESCO_VERSION,
        "evaluation_basis": EVALUATION_BASIS,
        "inexact_match_basis": INEXACT_BASIS,
        "verdicts": {
            "same": verdicts["same"],
            "narrower-or-broader": verdicts["narrower-or-broader"],
            "wrong": verdicts["wrong"],
            "unjudged": verdicts["unjudged"],
        },
        "verdict_sources": dict(sorted(sources.items())),
        "occupation": {
            **occupation.readings(),
            "true_negatives": true_negatives,
            "correct_refusals": correct_refusals,
            "incorrect_refusals": incorrect_refusals,
            "narrower_or_broader_rows": occupation_inexact,
        },
        # No refusal counters on the skill side: the sample compares URI sets there and cannot
        # say "expect nothing for this concept", so reporting a zero would invent a measurement.
        "skill": {
            **skill.readings(),
            "narrower_or_broader_rows": skill_inexact,
        },
        "collision_census": {
            "basis": COLLISION_BASIS,
            "occupation": _collision_census(refs.occupations, audited["occupation"]),
            "skill": _collision_census(refs.skills, audited["skill"]),
        },
    }


def main() -> int:
    report = evaluate()
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {REPORT.relative_to(ROOT)} ({report['sample_size']} reviewed postings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
