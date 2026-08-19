-- Genuine invariants: they must hold for the sample and for live partitions alike.
-- Sample-only expectations live in assert_sample_coverage_fixtures.sql, which live-site excludes.

select source, scope_id, sweep_id, coverage_status
from {{ ref('source_coverage') }}
where coverage_status != 'covered'

union all

select source, scope_id, sweep_id, freshness_status
from {{ ref('source_coverage') }}
where freshness_status not in ('fresh', 'stale', 'unknown')
