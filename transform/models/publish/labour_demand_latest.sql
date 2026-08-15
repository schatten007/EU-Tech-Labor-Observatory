{{
  config(
    materialized = 'view',
  )
}}

select
    sweeps.source,
    sweeps.scope_id,
    sweeps.partition_id,
    sweeps.sweep_id,
    sweeps.run_id,
    sweeps.expected_country as country,
    sweeps.observed_at,
    sweeps.started_at,
    sweeps.completed_at,
    sweeps.status,
    sweeps.hmac_key_version,
    sweeps.source_version,
    sweeps.licence_reference,
    sweeps.access_method,
    sweeps.approval_status,
    sweeps.coverage_limitations,
    coverage.freshness_age_hours,
    coverage.freshness_status,
    coverage.coverage_status,
    count(postings.source_id)::bigint as active_postings
from {{ ref('latest_complete_sweeps') }} as sweeps
left join {{ ref('stg_postings') }} as postings
    on postings.source = sweeps.source
    and postings.scope_id = sweeps.scope_id
    and postings.sweep_id = sweeps.sweep_id
inner join {{ ref('source_coverage') }} as coverage
    on coverage.source = sweeps.source
    and coverage.scope_id = sweeps.scope_id
    and coverage.sweep_id = sweeps.sweep_id
where coverage.coverage_status = 'covered'
group by all
