{{
  config(
    materialized = 'view',
  )
}}

select
    source,
    scope_id,
    partition_id,
    sweep_id,
    run_id,
    observed_at,
    started_at,
    completed_at,
    status,
    row_count,
    hmac_key_version
from {{ ref('stg_collection_manifests') }}
qualify row_number() over (
    partition by source, scope_id
    order by observed_at desc, completed_at desc, sweep_id desc
) = 1
