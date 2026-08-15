{{
  config(
    materialized = 'view',
  )
}}

select
    sweeps.source,
    sweeps.scope_id,
    sweeps.partition_id,
    sweeps.sweep_id,
    sweeps.run_id,
    postings.country,
    sweeps.observed_at,
    sweeps.started_at,
    sweeps.completed_at,
    sweeps.status,
    sweeps.hmac_key_version,
    count(postings.source_id)::bigint as active_postings
from {{ ref('latest_complete_sweeps') }} as sweeps
left join {{ ref('stg_postings') }} as postings
    on postings.source = sweeps.source
    and postings.scope_id = sweeps.scope_id
    and postings.sweep_id = sweeps.sweep_id
group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
