-- The machine-checkable form of the design decision behind requirement_demand_latest: every
-- posting in the latest sweep lands in exactly one row per dimension, so each dimension's
-- posting_count sums to that sweep's posting total. Deliberately untagged, so it runs against live
-- partitions under make live-site as well as against the synthetic sample: this is precisely the
-- class of fault that went unnoticed in Increment 13a, where the occupation ranking truncated at
-- DIMENSION_LIMIT and quietly stopped summing to its own published denominator while
-- release_check.py reported zero problems.

-- A dimension that does not reconcile: a dropped `Not stated` bucket, a silently discarded
-- unrecognised code, or a duplicated posting would all show up here.
select
    requirements.source,
    requirements.scope_id,
    requirements.sweep_id,
    requirements.dimension
from (
    select source, scope_id, sweep_id, dimension, sum(posting_count) as counted
    from {{ ref('requirement_demand_latest') }}
    group by 1, 2, 3, 4
) as requirements
inner join (
    select
        postings.source,
        postings.scope_id,
        postings.sweep_id,
        count(distinct postings.source_id) as postings_total
    from {{ ref('stg_postings') }} as postings
    inner join {{ ref('latest_complete_sweeps') }} as latest
        on latest.source = postings.source
        and latest.scope_id = postings.scope_id
        and latest.sweep_id = postings.sweep_id
    group by 1, 2, 3
) as sweeps
    on sweeps.source = requirements.source
    and sweeps.scope_id = requirements.scope_id
    and sweeps.sweep_id = requirements.sweep_id
where requirements.counted != sweeps.postings_total

union all

-- One row per dimension and value. A duplicate would double a published bucket while the column
-- total stayed plausible, and the sum above cannot see it on its own.
select source, scope_id, sweep_id, dimension
from {{ ref('requirement_demand_latest') }}
group by 1, 2, 3, 4, value_code, value_label
having count(*) > 1

union all

-- All three dimensions or none. A sweep collected before the fields existed publishes nothing here
-- and is not a fault; a sweep that published one dimension and lost another is, and the sum check
-- above would never see the missing one because it joins on the dimension.
select source, scope_id, sweep_id, 'incomplete-dimensions'::varchar as dimension
from {{ ref('requirement_demand_latest') }}
group by 1, 2, 3
having count(distinct dimension) != 3
