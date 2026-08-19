{{ config(tags=['sample_fixture']) }}

-- Pins the synthetic sample's coverage fixtures: the deliberate zero-row sweep, and one fresh
-- plus one stale scope so both freshness states stay rendered. Live partitions contain neither,
-- so live-site excludes tag:sample_fixture.

select 'jobtech' as source, 'jobtech-empty-scope' as scope_id, 'missing' as sweep_id,
    'missing' as detail
where not exists (
    select 1
    from {{ ref('source_coverage') }}
    where scope_id = 'jobtech-empty-scope'
        and country = 'SE'
        and observed_rows = 0
        and coverage_status = 'covered'
)

union all

select 'jobtech', 'freshness-fixture', 'missing', 'fresh-and-stale-required'
where not exists (
    select 1 from {{ ref('source_coverage') }} where freshness_status = 'fresh'
)
or not exists (
    select 1 from {{ ref('source_coverage') }} where freshness_status = 'stale'
)
