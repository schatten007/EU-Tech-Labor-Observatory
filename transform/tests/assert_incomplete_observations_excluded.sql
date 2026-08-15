with incomplete_observations as (
    select
        postings.source,
        postings.scope_id,
        postings.sweep_id,
        postings.source_id,
        cast(postings.observed_at as timestamp) as observed_at
    from read_json(
        '{{ env_var('OBSERVATIONS_PATH', 'data/sample/postings_sample.ndjson') }}',
        format = 'newline_delimited',
        columns = {
            source: 'varchar',
            source_id: 'varchar',
            scope_id: 'varchar',
            sweep_id: 'varchar',
            observed_at: 'varchar'
        }
    ) as postings
    inner join {{ source('manifests', 'sweeps') }} as manifests
        on manifests.source = postings.source
        and manifests.scope_id = postings.scope_id
        and manifests.sweep_id = postings.sweep_id
        and cast(manifests.observed_at as timestamp) = cast(postings.observed_at as timestamp)
    where manifests.status != 'complete'
)

select incomplete_observations.source, incomplete_observations.scope_id, incomplete_observations.sweep_id
from incomplete_observations
inner join {{ ref('stg_postings') }} as staged
    on staged.source = incomplete_observations.source
    and staged.scope_id = incomplete_observations.scope_id
    and staged.sweep_id = incomplete_observations.sweep_id
    and staged.source_id = incomplete_observations.source_id
