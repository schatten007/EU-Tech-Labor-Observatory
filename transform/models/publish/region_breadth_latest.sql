{{
  config(
    materialized = 'view',
  )
}}

-- Region breadth per (source, scope_id): how many NUTS-3 regions carry at least one mapped
-- posting in the latest complete sweep, against the count of NUTS-3 regions in the pinned
-- reference frame for that country. A count, never a share: 393 of 400 is a statement of
-- coverage, not a percentage claim. The frame comes from stg_nuts_labels (nine reference CSVs,
-- one row per nuts_code), not from geography_nuts_2024.csv alone, which is Sweden-only.
-- Breadth must not be taken from the rendered region rows: dimension_demand_latest is complete
-- here, but the publisher truncates the ranking at DIMENSION_LIMIT = 25, so the page's table
-- cannot answer this question. Left join so a country with no pinned NUTS-3 frame yields a null
-- denominator rather than a wrong one.

with mapped as (
    select
        demand.source,
        demand.scope_id,
        sweeps.expected_country as country,
        count(distinct demand.value_uri)::bigint as regions_with_postings
    from {{ ref('dimension_demand_latest') }} as demand
    inner join {{ ref('latest_complete_sweeps') }} as sweeps
        on sweeps.source = demand.source
        and sweeps.scope_id = demand.scope_id
    where demand.dimension = 'region'
    group by all
),
frame as (
    select
        left(nuts_code, 2) as country,
        count(distinct nuts_code)::bigint as regions_in_frame
    from {{ ref('stg_nuts_labels') }}
    where length(nuts_code) = 5
    group by all
)
select
    mapped.source,
    mapped.scope_id,
    mapped.country,
    mapped.regions_with_postings,
    frame.regions_in_frame
from mapped
left join frame
    on frame.country = mapped.country
