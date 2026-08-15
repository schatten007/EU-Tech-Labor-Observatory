select postings.source, postings.scope_id, postings.sweep_id, postings.source_id
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
left join {{ source('manifests', 'sweeps') }} as sweeps
    on sweeps.source = postings.source
    and sweeps.scope_id = postings.scope_id
    and sweeps.sweep_id = postings.sweep_id
    and sweeps.observed_at = cast(postings.observed_at as timestamp)
where sweeps.sweep_id is null
