"""Pure, stdlib-only rules that turn the published rows into stated findings.

Every rule returns `None` when its preconditions are unmet: silence beats a
hedge, and no rule softens a claim to keep a sentence. The trend gate
constants and the full precondition list are pre-registered in SESSIONS.md
under Increment 16.

The module is pure by construction - rows in, `Insight` or `None` out, no
querying, no I/O, no clock - so every rule is testable offline and every
numeric token in a generated sentence can be proven to appear in the rows it
was built from.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

# Row shapes mirror scripts/publish.py: this module never queries, so the two
# must agree by test rather than by construction.
DemandRow = tuple[str, str, str | None, datetime, int, str, str, str, str, str]
CoverageRow = tuple[
    str, str, str | None, datetime, int, int, str, str, float | None, str | None, int | None
]
DimensionRow = tuple[str, str, str, int]
RequirementRow = tuple[str, str, str | None, str, int]
MappingCoverageRow = tuple[str, str, str, int, int, int]
# The scope-keyed rows build() partitions on before any rule runs: (source, scope_id)
# prefixed onto the published row, so a two-scope page never pools into one rule call.
# The rules keep their existing signatures and receive one scope's rows, unscoped.
ScopedDimensionRow = tuple[str, str, str, str, str, int]
ScopedRequirementRow = tuple[str, str, str, str, str | None, str, int]
FlowRow = tuple[str, str, datetime, int | None, int | None, int | None, int | None, str]
SurvivalRow = tuple[
    str,
    str,
    bool,
    int | None,
    int | None,
    float | None,
    float | None,
    float | None,
    int | None,
    str,
]
FrequencyRow = tuple[str, int, datetime, datetime, float | None, int | None, str | None, str]

Evidence = dict[str, int | float | str]

# Pre-registered in SESSIONS.md before any figure was computed. Seven days is
# the shortest span that contains every weekday once, so a day-over-day claim
# cannot be a working-week cycle; 14 complete sweeps is two per day across that
# span, the weakest cadence at which two adjacent daily readings are taken at
# comparable points in their days.
TREND_MIN_SWEEPS = 14
TREND_MIN_SPAN_DAYS = 7

# The requirement codes the share rules read, pinned in schema.yml and in
# data/reference/jobtech_requirement_labels.csv.
PERMANENT_EMPLOYMENT_CODE = "kpPX_CNN_gDU"
FIXED_TERM_EMPLOYMENT_CODE = "sTu5_NBQ_udq"
FULL_TIME_CODE = "6YE1_gAC_R2G"
PART_TIME_CODE = "947z_JGS_Uk2"

CLOSED_LIFECYCLES = frozenset({"source_reported", "inferred_absence"})


@dataclass(frozen=True)
class Insight:
    """One generated sentence: the scope it describes, the text, and the numbers used."""

    scope: str
    text: str
    evidence: Evidence


def _present(items: Sequence[Insight | None]) -> list[Insight]:
    return [item for item in items if item is not None]


def _collecting_scopes(demand: Sequence[DemandRow]) -> list[str]:
    """Every scope with active postings, in demand order, so the largest scope leads.

    A zero-posting scope collects nothing, so no sentence may be drawn from it; a scope
    absent from demand has no sweep to name. Deduplicated because a scope_id names a
    (source, scope_id) pair in every row this module reads.
    """
    scopes: list[str] = []
    for row in demand:
        if row[4] > 0 and row[1] not in scopes:
            scopes.append(row[1])
    return scopes


def _coverage_row(
    coverage: Sequence[MappingCoverageRow], scope: str, dimension: str
) -> MappingCoverageRow | None:
    return next((row for row in coverage if row[1] == scope and row[2] == dimension), None)


def _requirement_count(
    requirements: Sequence[RequirementRow], dimension: str, code: str
) -> int | None:
    for row in requirements:
        if row[0] == dimension and row[2] == code:
            return row[4]
    return None


def _most_requested(
    rows: Sequence[DimensionRow], coverage_row: MappingCoverageRow | None
) -> tuple[str, int, int, int] | None:
    """(label, posting_count, postings_mapped, postings_total) for a unique leader."""
    if coverage_row is None:
        return None
    total, mapped = coverage_row[3], coverage_row[5]
    if total <= 0 or mapped <= 0 or mapped > total:
        return None
    if not rows:
        return None
    leader = rows[0]
    label, count = leader[1], leader[3]
    if not label or count <= 0 or count > mapped:
        return None
    if len(rows) > 1 and rows[1][3] == count:
        return None
    return label, count, mapped, total


def build(
    demand: Sequence[DemandRow],
    coverage: Sequence[CoverageRow],
    occupations: Sequence[ScopedDimensionRow],
    skills: Sequence[ScopedDimensionRow],
    mapping_coverage: Sequence[MappingCoverageRow],
    requirements: Sequence[ScopedRequirementRow],
    survival: Sequence[SurvivalRow],
    flows: Sequence[FlowRow],
    frequency: Sequence[FrequencyRow],
) -> dict[str, list[Insight]]:
    """Run every rule over the rows publish.py renders, keyed by section slug.

    One pass per collecting scope: the scope-keyed rows are partitioned here, so every
    rule receives only its own scope's rows under its existing signature. That partition
    is what keeps `_requirement_count` and the requirement-share totals reading one
    scope instead of the first code match across all of them.
    """
    results: dict[str, list[Insight]] = {}
    for scope in _collecting_scopes(demand):
        scope_occupations = [row[2:] for row in occupations if row[1] == scope]
        scope_skills = [row[2:] for row in skills if row[1] == scope]
        scope_requirements = [row[2:] for row in requirements if row[1] == scope]
        for slug, produced in (
            ("overview", [rule_latest_count(demand, scope)]),
            ("status", [rule_freshness_warning(coverage, scope)]),
            (
                "occupations",
                [
                    rule_most_requested_occupation(scope_occupations, mapping_coverage, scope),
                    rule_most_requested_skill(scope_skills, mapping_coverage, scope),
                ],
            ),
            (
                "requirements",
                [
                    rule_employment_shares(scope_requirements, scope),
                    rule_working_hours_shares(scope_requirements, scope),
                ],
            ),
            (
                "survival",
                [rule_median_duration(survival, scope), rule_trend(flows, frequency, scope)],
            ),
        ):
            results.setdefault(slug, []).extend(_present(produced))
    return results


def rule_latest_count(demand: Sequence[DemandRow], scope: str) -> Insight | None:
    """The latest complete sweep's active postings, with the sweep's date."""
    row = next((candidate for candidate in demand if candidate[1] == scope), None)
    if row is None or row[4] <= 0:
        return None
    active, observed_at = row[4], row[3]
    return Insight(
        scope=scope,
        text=(
            f"The latest complete sweep observed {active:,} active posting(s) "
            f"on {observed_at:%Y-%m-%d}."
        ),
        evidence={"active_postings": active, "observed_at": observed_at.strftime("%Y-%m-%d")},
    )


def rule_most_requested_occupation(
    occupations: Sequence[DimensionRow],
    coverage: Sequence[MappingCoverageRow],
    scope: str,
) -> Insight | None:
    """The leading occupation, stated against its mapped-posting denominator."""
    picked = _most_requested(occupations, _coverage_row(coverage, scope, "occupation"))
    if picked is None:
        return None
    label, count, mapped, total = picked
    return Insight(
        scope=scope,
        text=(
            f"The most frequently mapped occupation is {label}, in {count:,} of "
            f"{mapped:,} mapped posting(s)."
        ),
        evidence={
            "value_label": label,
            "posting_count": count,
            "postings_mapped": mapped,
            "postings_total": total,
        },
    )


def rule_most_requested_skill(
    skills: Sequence[DimensionRow],
    coverage: Sequence[MappingCoverageRow],
    scope: str,
) -> Insight | None:
    """The leading skill, stated as a count against its postings-with-a-mapped-skill."""
    picked = _most_requested(skills, _coverage_row(coverage, scope, "skill"))
    if picked is None:
        return None
    label, count, mapped, _total = picked
    return Insight(
        scope=scope,
        text=(
            f"The most frequently mapped skill is {label}, asked for in {count:,} of "
            f"{mapped:,} posting(s) with a mapped skill."
        ),
        evidence={"value_label": label, "posting_count": count, "postings_mapped": mapped},
    )


def rule_employment_shares(requirements: Sequence[RequirementRow], scope: str) -> Insight | None:
    """Permanent and fixed-term employment as exact counts against the employment-type total.

    A percentage would be a derived token the rows cannot vouch for, so the
    sentence states the two counts and the total and lets the reader see the
    share.
    """
    total = sum(row[4] for row in requirements if row[0] == "employment_type")
    permanent = _requirement_count(requirements, "employment_type", PERMANENT_EMPLOYMENT_CODE)
    fixed_term = _requirement_count(requirements, "employment_type", FIXED_TERM_EMPLOYMENT_CODE)
    if permanent is None or fixed_term is None or total <= 0:
        return None
    if permanent + fixed_term > total or permanent <= 0 or fixed_term <= 0:
        return None
    return Insight(
        scope=scope,
        text=(
            f"Of {total:,} postings in the latest sweep, {permanent:,} are permanent "
            f"employment and {fixed_term:,} are fixed-term employment."
        ),
        evidence={
            "employment_type_total": total,
            "permanent_employment": permanent,
            "fixed_term_employment": fixed_term,
        },
    )


def rule_working_hours_shares(requirements: Sequence[RequirementRow], scope: str) -> Insight | None:
    """Full-time and part-time as exact counts against the working-hours-type total."""
    total = sum(row[4] for row in requirements if row[0] == "working_hours_type")
    full_time = _requirement_count(requirements, "working_hours_type", FULL_TIME_CODE)
    part_time = _requirement_count(requirements, "working_hours_type", PART_TIME_CODE)
    if full_time is None or part_time is None or total <= 0:
        return None
    if full_time + part_time > total or full_time <= 0 or part_time <= 0:
        return None
    return Insight(
        scope=scope,
        text=(
            f"Of {total:,} postings in the latest sweep, {full_time:,} are full-time and "
            f"{part_time:,} are part-time."
        ),
        evidence={
            "working_hours_total": total,
            "full_time": full_time,
            "part_time": part_time,
        },
    )


def rule_median_duration(survival: Sequence[SurvivalRow], scope: str) -> Insight | None:
    """Median observed duration of the closed postings, with the censoring caveat.

    Only one closed basis may exist: the view publishes medians per lifecycle
    basis, and no sentence can state a single "the closed median" that pools
    them.
    """
    closed = [row for row in survival if row[0] == scope and row[1] in CLOSED_LIFECYCLES]
    if len(closed) != 1:
        return None
    status, censored, postings, median = closed[0][1], closed[0][2], closed[0][3], closed[0][5]
    if censored or postings is None or postings <= 0 or median is None:
        return None
    return Insight(
        scope=scope,
        text=(
            f"The median observed duration is {median:.1f} days across the {postings:,} "
            "closed posting(s); postings still open are right-censored and are excluded."
        ),
        evidence={
            "lifecycle_status": status,
            "posting_count": postings,
            "median_duration_days": median,
        },
    )


def rule_freshness_warning(coverage: Sequence[CoverageRow], scope: str) -> Insight | None:
    """State which freshness or coverage condition is unmet, and nothing else.

    A scope that is fresh and covered publishes no sentence: an absence of a
    warning is not itself a finding.
    """
    row = next((candidate for candidate in coverage if candidate[1] == scope), None)
    if row is None:
        return None
    freshness, coverage_status, age = row[6], row[7], row[8]
    if freshness == "fresh" and coverage_status == "covered":
        return None
    clauses: list[str] = []
    evidence: Evidence = {}
    if freshness == "stale":
        if age is not None:
            clauses.append(f"the latest sweep is {age:.0f} hours old, past its freshness threshold")
            evidence["freshness_age_hours"] = age
        else:
            clauses.append("the latest sweep is past its freshness threshold")
    elif freshness == "unknown":
        clauses.append("the latest sweep has unknown freshness")
    if coverage_status == "invalid":
        expected, observed = row[4], row[5]
        clauses.append(f"it stored {observed:,} of {expected:,} expected row(s)")
        evidence["observed_rows"] = observed
        evidence["expected_rows"] = expected
    elif coverage_status == "unknown_metadata":
        clauses.append(
            "its coverage is uncertified because sweep approval or metadata is incomplete"
        )
    if not clauses:
        return None
    return Insight(
        scope=scope,
        text="Read the figures with care: " + "; ".join(clauses) + ".",
        evidence=evidence,
    )


def rule_trend(
    flows: Sequence[FlowRow], frequency: Sequence[FrequencyRow], scope: str
) -> Insight | None:
    """Change between the two most recent adjacent daily buckets, when the gate is met.

    The two most recent observed buckets must be adjacent, and neither may be a
    suppressed or never-observed bucket: a gap next to the newest bucket
    silences the rule, and it never searches backwards for an older pair.
    """
    daily = sorted(
        (row for row in flows if row[0] == scope and row[1] == "day"),
        key=lambda row: row[2],
    )
    if len(daily) < 2:
        return None
    older, newer = daily[-2], daily[-1]
    if (newer[2] - older[2]).days != 1:
        return None
    before, after = older[5], newer[5]
    if before is None or after is None:
        return None
    cadence = next((row for row in frequency if row[0] == scope), None)
    if cadence is None or cadence[1] < TREND_MIN_SWEEPS:
        return None
    span_days = (cadence[3] - cadence[2]).days
    if span_days < TREND_MIN_SPAN_DAYS:
        return None
    evidence: Evidence = {
        "before": before,
        "after": after,
        "before_date": older[2].strftime("%Y-%m-%d"),
        "after_date": newer[2].strftime("%Y-%m-%d"),
        "complete_sweeps": cadence[1],
        "span_days": span_days,
    }
    if after > before:
        direction = "rose"
    elif after < before:
        direction = "fell"
    else:
        return Insight(
            scope=scope,
            text=(
                f"Active postings were unchanged at {before:,} between "
                f"{older[2]:%Y-%m-%d} and {newer[2]:%Y-%m-%d}."
            ),
            evidence=evidence,
        )
    return Insight(
        scope=scope,
        text=(
            f"Active postings {direction} from {before:,} on {older[2]:%Y-%m-%d} to "
            f"{after:,} on {newer[2]:%Y-%m-%d}."
        ),
        evidence=evidence,
    )
