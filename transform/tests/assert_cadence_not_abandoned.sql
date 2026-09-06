-- Cadence guard (Plan 1 Task 3): fail loudly when a scope's collection has been abandoned.
--
-- Problem: staleness is published as a page badge (source_coverage.freshness_status), which
-- only a human reading the page notices. Eleven days of Swedish silence (2026-08-22 to
-- 2026-09-04) produced no signal anywhere in the repo. This test turns *abandonment* into a
-- red gate while ordinary staleness stays a badge: it fires only when a scope's latest
-- complete sweep is older than a generous multiple (4x) of its own freshness threshold.
--
-- Reference time: read through the same OBSERVATORY_REFERENCE_TIME mechanism as
-- source_coverage (Makefile exports it for live-site; the synthetic sample falls back to its
-- pinned 2026-08-15T12:00:00Z default). On that sample the largest threshold multiple is
-- 171/48 = 3.6x (the deliberately stale keyword scope), so 4x is green on the sample by
-- design and red on a scope idle ~2 weeks against a 48 h threshold -- the exact 2026-09-04
-- situation this test exists to catch. If that ever reddens `make check` on the sample, the
-- sample changed; investigate the sample, never this multiple.
--
-- The latest complete sweep per (source, scope_id) is the same grain source_coverage
-- publishes; a scope with zero complete sweeps is absent here and is the live-site build's
-- own fail-closed case, not this test's.

with latest as (
    select source, scope_id, observed_at, freshness_threshold_hours
    from {{ ref('stg_collection_manifests') }}
    qualify row_number() over (
        partition by source, scope_id
        order by observed_at desc, completed_at desc, sweep_id desc
    ) = 1
),
aged as (
    select
        source,
        scope_id,
        observed_at,
        freshness_threshold_hours,
        date_diff(
            'second',
            observed_at,
            cast('{{ env_var('OBSERVATORY_REFERENCE_TIME', '2026-08-15T12:00:00Z') }}' as timestamp)
        ) / 3600.0 as age_hours
    from latest
)
select
    'cadence abandoned' as failure,
    source,
    scope_id,
    observed_at,
    age_hours,
    freshness_threshold_hours
from aged
where freshness_threshold_hours is not null
    and age_hours > 4 * freshness_threshold_hours
