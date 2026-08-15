with observed as (
    select source, scope_id, sweep_id, count(*) as row_count
    from {{ ref('stg_postings') }}
    group by 1, 2, 3
)

select sweeps.source, sweeps.scope_id, sweeps.sweep_id
from {{ ref('stg_collection_manifests') }} as sweeps
left join observed
    on observed.source = sweeps.source
    and observed.scope_id = sweeps.scope_id
    and observed.sweep_id = sweeps.sweep_id
where sweeps.row_count != coalesce(observed.row_count, 0)
