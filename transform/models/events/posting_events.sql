{{
  config(
    materialized = 'view',
  )
}}

-- ponytail: observed_at identifies a complete source sweep. Add a collection-scope key
-- before partial or differently partitioned sweeps feed this model.
with snapshots as (
    select distinct source, observed_at
    from {{ ref('stg_postings') }}
),

last_seen as (
    select
        source,
        source_id,
        max(observed_at) as last_seen_at,
        min(removed_at) as removed_at
    from {{ ref('stg_postings') }}
    group by 1, 2
),

closures as (
    select
        postings.source,
        postings.source_id,
        coalesce(postings.removed_at, min(snapshots.observed_at)) as event_at,
        'closure'::varchar as event_type,
        case
            when postings.removed_at is not null then 'source_reported'
            else 'inferred_absence'
        end::varchar as event_basis
    from last_seen as postings
    left join snapshots
        on snapshots.source = postings.source
        and snapshots.observed_at > postings.last_seen_at
    group by 1, 2, postings.removed_at
    having postings.removed_at is not null or min(snapshots.observed_at) is not null
)

select
    source,
    source_id,
    observed_at as event_at,
    'presence'::varchar as event_type,
    'observed'::varchar as event_basis
from {{ ref('stg_postings') }}

union all

select source, source_id, event_at, event_type, event_basis
from closures
