{{ config(tags=['sample_fixture']) }}

-- The zero-row sweep exists only in the synthetic sample, so live-site excludes this tag.

select source, scope_id, sweep_id
from {{ ref('latest_complete_sweeps') }}
where scope_id = 'jobtech-empty-scope'
    and (sweep_id != '20260806T100000Z-empty' or row_count != 0)

union all

select 'jobtech', 'jobtech-empty-scope', 'missing'
where not exists (
    select 1
    from {{ ref('latest_complete_sweeps') }}
    where scope_id = 'jobtech-empty-scope'
)
