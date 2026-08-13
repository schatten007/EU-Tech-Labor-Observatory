{{
  config(
    materialized = 'view',
  )
}}

with latest_sweeps as (
    select source, max(observed_at) as observed_at
    from {{ ref('stg_postings') }}
    group by 1
)

select
    postings.source,
    postings.country,
    postings.observed_at,
    count(*)::bigint as active_postings
from {{ ref('stg_postings') }} as postings
inner join latest_sweeps
    on latest_sweeps.source = postings.source
    and latest_sweeps.observed_at = postings.observed_at
group by 1, 2, 3
