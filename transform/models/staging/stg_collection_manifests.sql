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
    cast(hmac_key_version as varchar) as hmac_key_version
from {{ source('manifests', 'sweeps') }}
where status = 'complete'
    and completed_at is not null
    and expected_pages = completed_pages
    and expected_rows = row_count
