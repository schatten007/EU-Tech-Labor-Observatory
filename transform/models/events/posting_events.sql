{{
  config(
    materialized = 'view',
  )
}}

with last_seen as (
    select
        source,
        scope_id,
        hmac_key_version,
        source_id,
        max(observed_at) as last_seen_at,
        arg_max(sweep_id, observed_at) as last_seen_sweep_id,
        min(removed_at) as removed_at
    from {{ ref('stg_postings') }}
    group by 1, 2, 3, 4
),

closures as (
    select
        postings.source,
        postings.scope_id,
        postings.hmac_key_version,
        postings.source_id,
        case
            when postings.removed_at is not null then postings.last_seen_sweep_id
            else arg_min(sweeps.sweep_id, sweeps.observed_at)
        end as sweep_id,
        coalesce(postings.removed_at, min(sweeps.observed_at)) as event_at,
        'closure'::varchar as event_type,
        case
            when postings.removed_at is not null then 'source_reported'
            else 'inferred_absence'
        end::varchar as event_basis
    from last_seen as postings
    left join {{ ref('stg_collection_manifests') }} as sweeps
        on sweeps.source = postings.source
        and sweeps.scope_id = postings.scope_id
        and sweeps.hmac_key_version = postings.hmac_key_version
        and sweeps.observed_at > postings.last_seen_at
    group by 1, 2, 3, 4, postings.last_seen_sweep_id, postings.removed_at
    having postings.removed_at is not null or min(sweeps.observed_at) is not null
)

select
    source,
    scope_id,
    hmac_key_version,
    source_id,
    sweep_id,
    observed_at as event_at,
    'presence'::varchar as event_type,
    'observed'::varchar as event_basis
from {{ ref('stg_postings') }}

union all

select source, scope_id, hmac_key_version, source_id, sweep_id, event_at, event_type, event_basis
from closures
