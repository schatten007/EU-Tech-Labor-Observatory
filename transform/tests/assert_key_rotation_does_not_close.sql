select source, scope_id, source_id, event_at
from {{ ref('posting_events') }}
where event_basis = 'inferred_absence'
    and event_at = timestamp '2026-08-08 09:00:00'
