{{
  config(
    materialized = 'view',
  )
}}

-- Posting survival by closure basis, within a single source and scope. Trends within a
-- stable source are meaningful; absolute cross-country comparisons are not published.
-- lifecycle_status: source_reported / inferred_absence removal, or active (still open,
-- so its duration is right-censored and is a lower bound, never a completed survival).
-- Small non-zero groups are suppressed to avoid singling out an individual posting.

with lifecycle as (
    select * from {{ ref('posting_lifecycle') }}
),

grouped as (
    select
        source,
        scope_id,
        lifecycle_status,
        count(*)::bigint as posting_count,
        sum(coalesce(advertised_vacancies, 0))::bigint as advertised_vacancies,
        bool_or(is_right_censored) as any_right_censored,
        median(posting_duration_days) as median_duration_days,
        quantile_cont(posting_duration_days, 0.25) as p25_duration_days,
        quantile_cont(posting_duration_days, 0.75) as p75_duration_days,
        max(posting_duration_days)::bigint as max_duration_days
    from lifecycle
    group by 1, 2, 3
)

select
    source,
    scope_id,
    lifecycle_status,
    {{ is_suppressed('posting_count') }}::boolean as is_suppressed,
    any_right_censored::boolean as any_right_censored,
    {{ mask_small('posting_count', 'posting_count') }}::bigint as posting_count,
    {{ mask_small('advertised_vacancies', 'posting_count') }}::bigint as advertised_vacancies,
    {{ mask_small('median_duration_days', 'posting_count') }}::double as median_duration_days,
    {{ mask_small('p25_duration_days', 'posting_count') }}::double as p25_duration_days,
    {{ mask_small('p75_duration_days', 'posting_count') }}::double as p75_duration_days,
    {{ mask_small('max_duration_days', 'posting_count') }}::bigint as max_duration_days
from grouped
