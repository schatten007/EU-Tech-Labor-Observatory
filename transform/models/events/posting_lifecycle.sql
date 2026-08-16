{{
  config(
    materialized = 'view',
  )
}}

-- Per-posting lifecycle fact: when a posting was first and last observed, how long it
-- lasted, and how it left the source. Duration measures posting survival in the source
-- (first observation to closure, or to last observation while still open). It is NOT a
-- time-to-hire: disappearance is recorded as a source-reported or inferred removal only.
-- Grain: one row per (source, scope_id, hmac_key_version, source_id), matching the event
-- log so a rotated HMAC key is treated as a distinct, unlinkable posting identity.

with seen as (
    select
        source,
        scope_id,
        hmac_key_version,
        source_id,
        min(observed_at) as first_seen_at,
        arg_min(sweep_id, observed_at) as first_seen_sweep_id,
        max(observed_at) as last_seen_at,
        arg_max(sweep_id, observed_at) as last_seen_sweep_id,
        count(distinct sweep_id) as observation_count,
        arg_max(number_of_vacancies, observed_at) as advertised_vacancies
    from {{ ref('stg_postings') }}
    group by 1, 2, 3, 4
),

closure as (
    select
        source,
        scope_id,
        hmac_key_version,
        source_id,
        event_at as closure_at,
        event_basis as closure_basis
    from {{ ref('posting_events') }}
    where event_type = 'closure'
)

select
    seen.source,
    seen.scope_id,
    seen.hmac_key_version,
    seen.source_id,
    seen.first_seen_at,
    seen.first_seen_sweep_id,
    seen.last_seen_at,
    seen.last_seen_sweep_id,
    seen.observation_count::bigint as observation_count,
    cast(seen.advertised_vacancies as bigint) as advertised_vacancies,
    closure.closure_at,
    closure.closure_basis,
    coalesce(closure.closure_basis, 'active')::varchar as lifecycle_status,
    (closure.closure_at is null)::boolean as is_right_censored,
    date_diff(
        'day',
        seen.first_seen_at,
        coalesce(closure.closure_at, seen.last_seen_at)
    )::bigint as posting_duration_days
from seen
left join closure
    on closure.source = seen.source
    and closure.scope_id = seen.scope_id
    and closure.hmac_key_version = seen.hmac_key_version
    and closure.source_id = seen.source_id
