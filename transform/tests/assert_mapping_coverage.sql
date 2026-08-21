-- Genuine invariants over the published denominator: they must hold for the sample and for live
-- partitions alike, so this test stays untagged and runs under live-site too.

-- The three counts narrow: a posting cannot be mapped without a source value, and a sweep that
-- published a coverage row must have had at least one posting to count.
select source, scope_id, sweep_id, dimension
from {{ ref('mapping_coverage_latest') }}
where postings_mapped > postings_with_source_value
    or postings_with_source_value > postings_total
    or postings_total < 1

union all

-- One row per dimension per sweep. A duplicate would double the denominator printed on the page
-- while the ranked numerator above it stayed the same.
select source, scope_id, sweep_id, dimension
from {{ ref('mapping_coverage_latest') }}
group by 1, 2, 3, 4
having count(*) > 1

union all

-- Region and occupation are scalar per posting, so their postings_total must agree with
-- mapping_quality_latest's total_outcomes for the same key. Skill is deliberately excluded: its
-- quality rows are per posting per skill, so its total_outcomes counts mappings and is expected to
-- exceed postings_total. Do not "fix" that asymmetry by adding skill here.
select coverage.source, coverage.scope_id, coverage.sweep_id, coverage.dimension
from {{ ref('mapping_coverage_latest') }} as coverage
inner join (
    select source, scope_id, sweep_id, dimension, max(total_outcomes) as total_outcomes
    from {{ ref('mapping_quality_latest') }}
    group by 1, 2, 3, 4
) as quality
    on quality.source = coverage.source
    and quality.scope_id = coverage.scope_id
    and quality.sweep_id = coverage.sweep_id
    and quality.dimension = coverage.dimension
where coverage.dimension in ('region', 'occupation')
    and quality.total_outcomes != coverage.postings_total
