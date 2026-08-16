{{
  config(
    materialized = 'view',
  )
}}

with latest as (
    select * from {{ ref('latest_complete_sweeps') }}
),
scalar as (
    select
        postings.source,
        postings.scope_id,
        postings.sweep_id,
        'region'::varchar as dimension,
        postings.region_mapping_status as mapping_status,
        postings.region_mapping_method as mapping_method,
        cast(null as varchar) as mapping_confidence,
        postings.nuts_version as taxonomy_version,
        count(distinct postings.source_id)::bigint as outcome_count
    from {{ ref('stg_postings') }} as postings
    inner join latest
        on latest.source = postings.source and latest.scope_id = postings.scope_id
        and latest.sweep_id = postings.sweep_id
    group by all
    union all
    select
        postings.source,
        postings.scope_id,
        postings.sweep_id,
        'occupation'::varchar as dimension,
        postings.occupation_mapping_status,
        postings.occupation_mapping_method,
        postings.occupation_mapping_confidence,
        postings.esco_version,
        count(distinct postings.source_id)::bigint
    from {{ ref('stg_postings') }} as postings
    inner join latest
        on latest.source = postings.source and latest.scope_id = postings.scope_id
        and latest.sweep_id = postings.sweep_id
    group by all
), skills as (
    select
        postings.source,
        postings.scope_id,
        postings.sweep_id,
        'skill'::varchar as dimension,
        skills.mapping_status,
        skills.mapping_method,
        skills.mapping_confidence,
        skills.esco_version as taxonomy_version,
        count(*)::bigint as outcome_count
    from {{ ref('stg_postings') }} as postings
    inner join latest
        on latest.source = postings.source and latest.scope_id = postings.scope_id
        and latest.sweep_id = postings.sweep_id
    inner join {{ ref('stg_skill_mappings') }} as skills
        on skills.source = postings.source and skills.scope_id = postings.scope_id
        and skills.sweep_id = postings.sweep_id and skills.source_id = postings.source_id
    group by all
)
select *, sum(outcome_count) over (partition by source, scope_id, sweep_id, dimension) as total_outcomes
from (
    select * from scalar
    union all
    select * from skills
)
