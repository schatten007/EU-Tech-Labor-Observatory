-- Published flow measures are never negative and never expose a non-zero group below the
-- disclosure threshold. Zero stays visible (an absence of postings is not disclosive).

select source, scope_id, grain, bucket_start
from {{ ref('posting_flows') }}
where
    coalesce(openings, 0) < 0
    or coalesce(closures, 0) < 0
    or coalesce(active_postings, 0) < 0
    or coalesce(active_vacancies, 0) < 0
    or (openings is not null and openings > 0 and openings < {{ small_count_threshold() }})
    or (closures is not null and closures > 0 and closures < {{ small_count_threshold() }})
    or (
        active_postings is not null
        and active_postings > 0
        and active_postings < {{ small_count_threshold() }}
    )
