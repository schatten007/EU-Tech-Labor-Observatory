{{
  config(
    materialized = 'view',
  )
}}

select
    postings.source,
    postings.source_id,
    postings.scope_id,
    postings.sweep_id,
    postings.hmac_key_version,
    postings.observed_at,
    (cast(skills.key as integer) + 1)::integer as skill_ordinal,
    cast(skills.value->>'uri' as varchar) as esco_skill_uri,
    cast(skills.value->>'label' as varchar) as esco_skill_label,
    cast(skills.value->>'status' as varchar) as mapping_status,
    cast(skills.value->>'confidence' as varchar) as mapping_confidence,
    cast(skills.value->>'method' as varchar) as mapping_method,
    cast(skills.value->>'jobtech_taxonomy_version' as varchar) as jobtech_taxonomy_version,
    cast(skills.value->>'esco_version' as varchar) as esco_version
from {{ ref('stg_postings') }} as postings
cross join lateral json_each(postings.skill_mappings) as skills
