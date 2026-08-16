{{
  config(
    materialized = 'view',
  )
}}

select
    cast(source as varchar) as source,
    cast(scope_id as varchar) as scope_id,
    cast(scope_hash as varchar) as scope_hash,
    cast(scope_json as varchar) as scope_json,
    cast(partition_id as varchar) as partition_id,
    cast(sweep_id as varchar) as sweep_id,
    cast(run_id as varchar) as run_id,
    cast(observed_at as timestamp) as observed_at,
    cast(started_at as timestamp) as started_at,
    cast(completed_at as timestamp) as completed_at,
    cast(status as varchar) as status,
    cast(expected_pages as integer) as expected_pages,
    cast(completed_pages as integer) as completed_pages,
    cast(expected_rows as bigint) as expected_rows,
    cast(row_count as bigint) as row_count,
    cast(hmac_key_version as varchar) as hmac_key_version,
    cast(source_version as varchar) as source_version,
    cast(licence_reference as varchar) as licence_reference,
    cast(access_method as varchar) as access_method,
    cast(approval_status as varchar) as approval_status,
    cast(expected_country as varchar) as expected_country,
    cast(freshness_threshold_hours as integer) as freshness_threshold_hours,
    cast(coverage_limitations as varchar) as coverage_limitations
    , cast(reference_hashes as varchar) as reference_hashes
    , cast(nuts_version as varchar) as nuts_version
    , cast(jobtech_taxonomy_version as varchar) as jobtech_taxonomy_version
    , cast(esco_version as varchar) as esco_version
from read_json(
    '{{ env_var('MANIFESTS_PATH', 'data/sample/sweeps_sample.ndjson') }}',
    format = 'auto',
    columns = {
        source: 'varchar', scope_id: 'varchar', scope_hash: 'varchar', scope_json: 'varchar',
        partition_id: 'varchar', sweep_id: 'varchar', run_id: 'varchar', observed_at: 'varchar',
        started_at: 'varchar', completed_at: 'varchar', status: 'varchar', expected_pages: 'integer',
        completed_pages: 'integer', expected_rows: 'bigint', row_count: 'bigint',
        hmac_key_version: 'varchar', source_version: 'varchar', licence_reference: 'varchar',
        access_method: 'varchar', approval_status: 'varchar', expected_country: 'varchar',
        freshness_threshold_hours: 'integer', coverage_limitations: 'varchar',
        reference_hashes: 'varchar', nuts_version: 'varchar',
        jobtech_taxonomy_version: 'varchar', esco_version: 'varchar'
    }
)
where status = 'complete'
    and completed_at is not null
    and expected_pages = completed_pages
    and expected_rows = row_count
