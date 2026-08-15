select events.source, events.scope_id, events.source_id, events.sweep_id
from {{ ref('posting_events') }} as events
left join {{ ref('stg_collection_manifests') }} as sweeps
    on sweeps.source = events.source
    and sweeps.scope_id = events.scope_id
    and sweeps.hmac_key_version = events.hmac_key_version
    and sweeps.sweep_id = events.sweep_id
where events.event_basis = 'inferred_absence'
    and (sweeps.sweep_id is null or sweeps.observed_at != events.event_at)
