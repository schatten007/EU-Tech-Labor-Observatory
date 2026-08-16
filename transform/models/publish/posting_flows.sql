{{
  config(
    materialized = 'view',
  )
}}

-- Openings, active stock, and closures over time within a single source and scope,
-- at daily, weekly, and monthly grain. Openings and closures are flows (counted in the
-- bucket where they happen); active stock is a point-in-time count taken at the last
-- sweep in the bucket. Posting counts and advertised vacancy counts are kept distinct.
-- Small non-zero cells are suppressed. Cross-source or cross-country sums are not built.

with grains as (
    select unnest(['day', 'week', 'month']) as grain
),

lifecycle as (
    select * from {{ ref('posting_lifecycle') }}
),

openings as (
    select
        lifecycle.source,
        lifecycle.scope_id,
        grains.grain,
        date_trunc(grains.grain, lifecycle.first_seen_at)::timestamp as bucket_start,
        count(*)::bigint as n_openings
    from lifecycle
    cross join grains
    group by 1, 2, 3, 4
),

closures as (
    select
        lifecycle.source,
        lifecycle.scope_id,
        grains.grain,
        date_trunc(grains.grain, lifecycle.closure_at)::timestamp as bucket_start,
        count(*)::bigint as n_closures
    from lifecycle
    cross join grains
    where lifecycle.closure_at is not null
    group by 1, 2, 3, 4
),

sweep_stock as (
    select
        sweeps.source,
        sweeps.scope_id,
        sweeps.observed_at,
        count(postings.source_id)::bigint as active_postings,
        sum(coalesce(postings.number_of_vacancies, 0))::bigint as active_vacancies
    from {{ ref('stg_collection_manifests') }} as sweeps
    left join {{ ref('stg_postings') }} as postings
        on postings.source = sweeps.source
        and postings.scope_id = sweeps.scope_id
        and postings.sweep_id = sweeps.sweep_id
    group by 1, 2, 3
),

stock as (
    select source, scope_id, grain, bucket_start, active_postings, active_vacancies
    from (
        select
            sweep_stock.source,
            sweep_stock.scope_id,
            grains.grain,
            date_trunc(grains.grain, sweep_stock.observed_at)::timestamp as bucket_start,
            sweep_stock.observed_at,
            sweep_stock.active_postings,
            sweep_stock.active_vacancies
        from sweep_stock
        cross join grains
    )
    qualify row_number() over (
        partition by source, scope_id, grain, bucket_start
        order by observed_at desc
    ) = 1
),

spine as (
    select source, scope_id, grain, bucket_start from openings
    union
    select source, scope_id, grain, bucket_start from closures
    union
    select source, scope_id, grain, bucket_start from stock
),

combined as (
    select
        spine.source,
        spine.scope_id,
        spine.grain,
        spine.bucket_start,
        coalesce(openings.n_openings, 0) as openings_raw,
        coalesce(closures.n_closures, 0) as closures_raw,
        stock.active_postings as active_postings_raw,
        stock.active_vacancies as active_vacancies_raw
    from spine
    left join openings
        on openings.source = spine.source
        and openings.scope_id = spine.scope_id
        and openings.grain = spine.grain
        and openings.bucket_start = spine.bucket_start
    left join closures
        on closures.source = spine.source
        and closures.scope_id = spine.scope_id
        and closures.grain = spine.grain
        and closures.bucket_start = spine.bucket_start
    left join stock
        on stock.source = spine.source
        and stock.scope_id = spine.scope_id
        and stock.grain = spine.grain
        and stock.bucket_start = spine.bucket_start
)

select
    source,
    scope_id,
    grain,
    bucket_start,
    (
        {{ is_suppressed('openings_raw') }}
        or {{ is_suppressed('closures_raw') }}
        or {{ is_suppressed('coalesce(active_postings_raw, 0)') }}
    )::boolean as is_suppressed,
    {{ mask_small('openings_raw', 'openings_raw') }}::bigint as openings,
    {{ mask_small('closures_raw', 'closures_raw') }}::bigint as closures,
    {{ mask_small('active_postings_raw', 'active_postings_raw') }}::bigint as active_postings,
    {{ mask_small('active_vacancies_raw', 'active_postings_raw') }}::bigint as active_vacancies
from combined
