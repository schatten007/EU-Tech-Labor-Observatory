-- Grain of the staging contract: one observation per (source, source_id, observed_at).
-- Duplicates here silently corrupt every survival number downstream, so this is the
-- one test that must never be waived.
-- ponytail: singular test instead of dbt_utils, which would need `dbt deps` and break
-- the offline GATE-0 requirement. Swap in dbt_utils if packages ever land.

select source, source_id, observed_at, count(*) as n_rows
from {{ ref('stg_postings') }}
group by 1, 2, 3
having count(*) > 1
