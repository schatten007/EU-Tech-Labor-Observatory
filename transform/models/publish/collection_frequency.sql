{{
  config(
    materialized = 'view',
  )
}}

-- Collection frequency and comparability metadata per source and scope, published beside
-- the trend metrics so cadence and known limitations are read together with the numbers.

with ordered as (
    select
        source,
        scope_id,
        observed_at,
        freshness_threshold_hours,
        coverage_limitations,
        date_diff(
            'hour',
            lag(observed_at) over (partition by source, scope_id order by observed_at),
            observed_at
        ) as gap_hours
    from {{ ref('stg_collection_manifests') }}
)

select
    source,
    scope_id,
    count(*)::bigint as complete_sweeps,
    min(observed_at)::timestamp as first_observed_at,
    max(observed_at)::timestamp as last_observed_at,
    median(gap_hours)::double as median_interval_hours,
    max(freshness_threshold_hours)::integer as freshness_threshold_hours,
    max(coverage_limitations)::varchar as coverage_limitations
from ordered
group by 1, 2
