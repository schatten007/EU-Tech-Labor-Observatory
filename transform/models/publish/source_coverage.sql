{{
  config(
    materialized = 'view',
  )
}}

with coverage as (
    select
        sweeps.source,
        sweeps.scope_id,
        sweeps.sweep_id,
        sweeps.expected_country as country,
        sweeps.observed_at,
        sweeps.row_count as expected_rows,
        count(postings.source_id)::bigint as observed_rows,
        count(postings.source_id) filter (
            where postings.country != sweeps.expected_country
        )::bigint as wrong_country_rows,
        sweeps.source_version,
        sweeps.licence_reference,
        sweeps.access_method,
        sweeps.approval_status,
        sweeps.freshness_threshold_hours,
        sweeps.coverage_limitations
    from {{ ref('stg_collection_manifests') }} as sweeps
    left join {{ ref('stg_postings') }} as postings
        on postings.source = sweeps.source
        and postings.scope_id = sweeps.scope_id
        and postings.sweep_id = sweeps.sweep_id
    group by all
)

select
    source,
    scope_id,
    sweep_id,
    country,
    observed_at,
    expected_rows,
    observed_rows,
    source_version,
    licence_reference,
    access_method,
    approval_status,
    freshness_threshold_hours,
    coverage_limitations,
    date_diff(
        'second',
        observed_at,
        cast('{{ env_var('OBSERVATORY_REFERENCE_TIME', '2026-08-15T12:00:00Z') }}' as timestamp)
    ) / 3600.0 as freshness_age_hours,
    case
        when freshness_threshold_hours is null then 'unknown'
        when date_diff(
            'second',
            observed_at,
            cast('{{ env_var('OBSERVATORY_REFERENCE_TIME', '2026-08-15T12:00:00Z') }}' as timestamp)
        ) / 3600.0 > freshness_threshold_hours then 'stale'
        else 'fresh'
    end::varchar as freshness_status,
    case
        when approval_status != 'approved'
            or source_version is null
            or licence_reference is null
            or access_method is null
            or country is null
            or freshness_threshold_hours is null then 'unknown_metadata'
        when observed_rows != expected_rows or wrong_country_rows > 0 then 'invalid'
        else 'covered'
    end::varchar as coverage_status
from coverage
