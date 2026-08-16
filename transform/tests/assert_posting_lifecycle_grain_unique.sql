select source, scope_id, hmac_key_version, source_id, count(*) as n_rows
from {{ ref('posting_lifecycle') }}
group by 1, 2, 3, 4
having count(*) > 1
