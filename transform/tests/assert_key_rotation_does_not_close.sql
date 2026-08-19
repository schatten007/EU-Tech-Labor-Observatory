{{ config(tags=['sample_fixture']) }}

-- Pinned to the sample's 20260808T090000Z-rotated sweep, so it cannot fire on live partitions.
-- The live-safe half of this guarantee is assert_no_cross_key_closures.sql.

select source, scope_id, source_id, event_at
from {{ ref('posting_events') }}
where event_basis = 'inferred_absence'
    and event_at = timestamp '2026-08-08 09:00:00'
