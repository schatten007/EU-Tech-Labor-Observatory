{{
  config(
    materialized = 'view',
  )
}}

with latest as (
    select * from {{ ref('latest_complete_sweeps') }}
),
base as (
    select
        postings.source,
        postings.scope_id,
        postings.sweep_id,
        postings.observed_at,
        postings.nuts_code,
        postings.nuts_label,
        postings.region_mapping_status,
        postings.region_mapping_method,
        postings.nuts_version,
        postings.esco_occupation_uri,
        postings.esco_occupation_label,
        postings.occupation_mapping_status,
        postings.occupation_mapping_confidence,
        postings.occupation_mapping_method,
        postings.jobtech_taxonomy_version,
        postings.esco_version,
        postings.source_id
    from {{ ref('stg_postings') }} as postings
    inner join latest
        on latest.source = postings.source
        and latest.scope_id = postings.scope_id
        and latest.sweep_id = postings.sweep_id
),
region as (
    select
        source, scope_id, sweep_id, observed_at, 'region'::varchar as dimension,
        nuts_code as value_uri, nuts_label as value_label, nuts_version as taxonomy_version,
        count(distinct source_id)::bigint as posting_count
    from base
    where region_mapping_status = 'mapped'
    group by all
), occupation as (
    select
        source, scope_id, sweep_id, observed_at, 'occupation'::varchar as dimension,
        esco_occupation_uri as value_uri, esco_occupation_label as value_label,
        esco_version as taxonomy_version, count(distinct source_id)::bigint as posting_count
    from base
    where occupation_mapping_status = 'mapped'
    group by all
)
select * from region
union all
select * from occupation
