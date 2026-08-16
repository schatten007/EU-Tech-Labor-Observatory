-- Suppressed survival cells must hide the count, advertised vacancies, and every duration
-- statistic; published cells must never expose a non-zero group below the threshold; and a
-- posting duration can never be negative.

select source, scope_id, lifecycle_status
from {{ ref('posting_survival') }}
where
    (is_suppressed and (
        posting_count is not null
        or advertised_vacancies is not null
        or median_duration_days is not null
        or p25_duration_days is not null
        or p75_duration_days is not null
        or max_duration_days is not null
    ))
    or (
        not is_suppressed
        and posting_count is not null
        and posting_count > 0
        and posting_count < {{ small_count_threshold() }}
    )
    or (max_duration_days is not null and max_duration_days < 0)
