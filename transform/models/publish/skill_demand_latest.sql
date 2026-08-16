{{
  config(
    materialized = 'view',
  )
}}

select
    postings.source,
    postings.scope_id,
    postings.sweep_id,
    postings.observed_at,
    'skill'::varchar as dimension,
    skills.esco_skill_uri as value_uri,
    skills.esco_skill_label as value_label,
    skills.esco_version as taxonomy_version,
    count(distinct postings.source_id)::bigint as posting_count
from {{ ref('stg_postings') }} as postings
inner join {{ ref('latest_complete_sweeps') }} as latest
    on latest.source = postings.source
    and latest.scope_id = postings.scope_id
    and latest.sweep_id = postings.sweep_id
inner join {{ ref('stg_skill_mappings') }} as skills
    on skills.source = postings.source
    and skills.scope_id = postings.scope_id
    and skills.sweep_id = postings.sweep_id
    and skills.source_id = postings.source_id
    and skills.mapping_status = 'mapped'
group by all
