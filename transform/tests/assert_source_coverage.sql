select source, scope_id, sweep_id, coverage_status
from {{ ref('source_coverage') }}
where coverage_status != 'covered'

union all

select source, scope_id, sweep_id, freshness_status
from {{ ref('source_coverage') }}
where freshness_status not in ('fresh', 'stale', 'unknown')

union all

select 'jobtech', 'jobtech-empty-scope', 'missing', 'missing'
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
