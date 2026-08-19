{{ config(tags=['sample_fixture']) }}

-- The zero-row sweep exists only in the synthetic sample, so live-site excludes this tag.

select source, scope_id, sweep_id, active_postings
from {{ ref('labour_demand_latest') }}
where scope_id = 'jobtech-empty-scope'
    and (sweep_id != '20260806T100000Z-empty' or active_postings != 0)

union all

select 'jobtech', 'jobtech-empty-scope', 'missing', -1
where not exists (
    select 1
    from {{ ref('labour_demand_latest') }}
    where scope_id = 'jobtech-empty-scope'
)
