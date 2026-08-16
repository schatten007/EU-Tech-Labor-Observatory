select
    source,
    scope_id,
    sweep_id,
    source_id,
    skill_ordinal,
    count(*) as duplicates
from {{ ref('stg_skill_mappings') }}
group by 1, 2, 3, 4, 5
having count(*) > 1
