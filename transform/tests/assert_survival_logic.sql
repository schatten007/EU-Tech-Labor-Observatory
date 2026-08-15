-- The synthetic timeline covers persistence, source-reported closure, and inferred
-- closure at the first later complete snapshot.

with expected as (
    select
        source, scope_id, hmac_key_version, source_id, sweep_id,
        timestamp '2026-08-10 10:00:00' as event_at,
        'closure'::varchar as event_type,
        'source_reported'::varchar as event_basis
    from {{ ref('stg_postings') }}
    where first_published = timestamp '2026-08-03 08:00:00'

    union all

    select
        source, scope_id, hmac_key_version, source_id, '20260806T090000Z-synthetic' as sweep_id,
        timestamp '2026-08-06 09:00:00' as event_at,
        'closure'::varchar as event_type,
        'inferred_absence'::varchar as event_basis
    from {{ ref('stg_postings') }}
    where first_published = timestamp '2026-08-04 08:00:00'
),

actual as (
    select source, scope_id, hmac_key_version, source_id, sweep_id, event_at, event_type, event_basis
    from {{ ref('posting_events') }}
    where event_type = 'closure'
)

(select * from expected except select * from actual)
union all
(select * from actual except select * from expected)
