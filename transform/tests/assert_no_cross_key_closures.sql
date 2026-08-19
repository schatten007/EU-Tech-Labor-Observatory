-- The live-safe half of the key-rotation guarantee. A rotated HMAC key changes every pseudonym,
-- so a sweep collected under a different key version must never be read as the absence that
-- closes a posting. Unlike assert_key_rotation_does_not_close.sql this pins no fixture date, so
-- it holds for the sample and for live partitions alike.

select events.source, events.scope_id, events.source_id, events.sweep_id
from {{ ref('posting_events') }} as events
join {{ ref('stg_collection_manifests') }} as sweeps
    on sweeps.source = events.source
    and sweeps.scope_id = events.scope_id
    and sweeps.sweep_id = events.sweep_id
where events.event_basis = 'inferred_absence'
    and sweeps.hmac_key_version != events.hmac_key_version
