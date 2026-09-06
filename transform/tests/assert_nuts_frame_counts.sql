-- The breadth denominator is the pinned NUTS-3 frame per country, read through stg_nuts_labels
-- (five-character codes are NUTS-3; the length filter keeps NUTS-1/2 rows out of the count).
-- Germany's 400 and Sweden's 21 are the figures 20b measured against the reference files; if
-- either differs, the frame changed and the published breadth line would be wrong — stop and
-- report, do not adjust the assertion to match. Untagged on purpose: it must fire under
-- live-site too.

select 'nuts frame count changed' as failure, frame.country, frame.regions_in_frame
from (
    select
        left(nuts_code, 2) as country,
        count(distinct nuts_code)::bigint as regions_in_frame
    from {{ ref('stg_nuts_labels') }}
    where length(nuts_code) = 5
    group by all
) as frame
where frame.country = 'DE' and frame.regions_in_frame != 400
    or frame.country = 'SE' and frame.regions_in_frame != 21
