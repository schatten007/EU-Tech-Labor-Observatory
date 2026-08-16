{{
  config(
    materialized = 'view',
  )
}}

select
    cast(postings.source as varchar) as source,
    cast(postings.source_id as varchar) as source_id,
    cast(postings.scope_id as varchar) as scope_id,
    cast(postings.sweep_id as varchar) as sweep_id,
    sweeps.hmac_key_version as hmac_key_version,
    cast(postings.observed_at as timestamp) as observed_at,
    try_cast(postings.first_published as timestamp) as first_published,
    try_cast(postings.last_modified as timestamp) as last_modified,
    try_cast(postings.removed_at as timestamp) as removed_at,
    cast(postings.nuts_code as varchar) as nuts_code,
    cast(postings.nuts_label as varchar) as nuts_label,
    cast(postings.region_mapping_status as varchar) as region_mapping_status,
    cast(postings.region_mapping_method as varchar) as region_mapping_method,
    cast(postings.nuts_version as varchar) as nuts_version,
    cast(postings.country as varchar) as country,
    cast(postings.esco_occupation_uri as varchar) as esco_occupation_uri,
    cast(postings.esco_occupation_label as varchar) as esco_occupation_label,
    cast(postings.occupation_mapping_status as varchar) as occupation_mapping_status,
    cast(postings.occupation_mapping_confidence as varchar) as occupation_mapping_confidence,
    cast(postings.occupation_mapping_method as varchar) as occupation_mapping_method,
    cast(postings.source_language as varchar) as source_language,
    cast(postings.jobtech_taxonomy_version as varchar) as jobtech_taxonomy_version,
    cast(postings.esco_version as varchar) as esco_version,
    postings.skill_mappings as skill_mappings,
    cast(postings.lang as varchar) as lang
from read_json(
    '{{ env_var('OBSERVATIONS_PATH', 'data/sample/postings_sample.ndjson') }}',
    format = 'newline_delimited',
    columns = {
        source: 'varchar',
        source_id: 'varchar',
        scope_id: 'varchar',
        sweep_id: 'varchar',
        observed_at: 'varchar',
        first_published: 'varchar',
        last_modified: 'varchar',
         removed_at: 'varchar',
         nuts_code: 'varchar',
         nuts_label: 'varchar', region_mapping_status: 'varchar',
         region_mapping_method: 'varchar', nuts_version: 'varchar',
         country: 'varchar',
         esco_occupation_uri: 'varchar',
         esco_occupation_label: 'varchar', occupation_mapping_status: 'varchar',
         occupation_mapping_confidence: 'varchar', occupation_mapping_method: 'varchar',
         source_language: 'varchar', jobtech_taxonomy_version: 'varchar', esco_version: 'varchar',
         skill_mappings: 'json', lang: 'varchar'
    }
) as postings
inner join {{ ref('stg_collection_manifests') }} as sweeps
    on sweeps.source = postings.source
    and sweeps.scope_id = postings.scope_id
    and sweeps.sweep_id = postings.sweep_id
    and sweeps.observed_at = cast(postings.observed_at as timestamp)
