select source, scope_id, sweep_id, source_id, count(*) as n_rows
from {{ ref('stg_postings') }}
group by 1, 2, 3, 4
having count(*) > 1
