{{
  config(
    materialized = 'view',
  )
}}

-- What the contract on offer actually is: permanent or fixed-term, full or part time, and how
-- long. Kept separate from dimension_demand_latest on purpose. These are JobTech Taxonomy v30
-- values, not NUTS or ESCO, and assert_mapping_outputs.sql pins that view's taxonomy_version to
-- ('NUTS-2024', '1.2.1'); folding them in would either break that assertion or force it to be
-- weakened, which is the opposite of what an audit needs.
--
-- Every posting in the latest sweep lands in exactly one row per dimension, so posting_count sums
-- to the sweep's posting total in each of the three dimensions and the table reconciles by
-- inspection with no denominator caveat. An unresolved value is published as a row, never dropped:
-- a value the source does not state becomes `Not stated` (not_present) and a code the reference
-- does not carry becomes `Unrecognised code` (unmapped) with its code kept. The alternative --
-- filtering to mapped values and stating a denominator in prose -- is exactly the shape that let
-- the truncated occupation ranking in Increment 13a stop summing to its own stated denominator
-- unnoticed. assert_requirement_totals.sql is the machine-checkable form of that invariant.
--
-- A NULL mapping_status is not a fourth bucket, it is a partition that predates the field, so those
-- rows are excluded rather than rendered as `Not stated`: the source did not decline to state a
-- working-hours type in 2026-08, we simply never collected it. Until a sweep is collected with the
-- keys, this view is legitimately empty and the section renders its empty state. A sweep that
-- somehow carried the status on only some of its postings would sum short of its own posting total,
-- which the totals assertion fails on rather than publishes.

with latest as (
    select * from {{ ref('latest_complete_sweeps') }}
),
base as (
    select
        postings.source,
        postings.scope_id,
        postings.sweep_id,
        postings.observed_at,
        postings.source_id,
        postings.employment_type_code,
        postings.employment_type_label,
        postings.employment_type_mapping_status,
        postings.working_hours_type_code,
        postings.working_hours_type_label,
        postings.working_hours_type_mapping_status,
        postings.duration_code,
        postings.duration_label,
        postings.duration_mapping_status
    from {{ ref('stg_postings') }} as postings
    inner join latest
        on latest.source = postings.source
        and latest.scope_id = postings.scope_id
        and latest.sweep_id = postings.sweep_id
),
employment_type as (
    select
        source, scope_id, sweep_id, observed_at, 'employment_type'::varchar as dimension,
        employment_type_code as value_code, employment_type_label as value_label,
        employment_type_mapping_status as mapping_status,
        count(distinct source_id)::bigint as posting_count
    from base
    where employment_type_mapping_status is not null
    group by all
), working_hours_type as (
    select
        source, scope_id, sweep_id, observed_at, 'working_hours_type'::varchar as dimension,
        working_hours_type_code as value_code, working_hours_type_label as value_label,
        working_hours_type_mapping_status as mapping_status,
        count(distinct source_id)::bigint as posting_count
    from base
    where working_hours_type_mapping_status is not null
    group by all
), duration as (
    select
        source, scope_id, sweep_id, observed_at, 'duration'::varchar as dimension,
        duration_code as value_code, duration_label as value_label,
        duration_mapping_status as mapping_status,
        count(distinct source_id)::bigint as posting_count
    from base
    where duration_mapping_status is not null
    group by all
)
-- The three branches are combined by naming every column, not with `select *`. A positional union
-- would keep compiling if one CTE's projection changed order, and it would publish one dimension's
-- codes under another dimension's labels -- permanently, for that sweep, since a stored partition
-- is never rewritten.
select
    source, scope_id, sweep_id, observed_at, dimension, value_code, value_label,
    mapping_status, posting_count
from employment_type
union all
select
    source, scope_id, sweep_id, observed_at, dimension, value_code, value_label,
    mapping_status, posting_count
from working_hours_type
union all
select
    source, scope_id, sweep_id, observed_at, dimension, value_code, value_label,
    mapping_status, posting_count
from duration
