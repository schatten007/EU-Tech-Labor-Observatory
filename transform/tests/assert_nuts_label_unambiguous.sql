-- stg_nuts_labels resolves one label per code with min(); a code carrying two distinct
-- non-null labels across the nine reference files would be silently collapsed. Surfaces
-- those conflicts instead of hiding them, so a precedence rule is a recorded decision,
-- not an accident. Untagged on purpose: it must fire under live-site too.

select 'nuts label conflict' as failure, conflict.nuts_code
from (
    select nuts_code
    from read_csv(
        [
            'data/reference/finland_tmt_region_nuts_2024.csv',
            'data/reference/francetravail_departements_nuts_2024.csv',
            'data/reference/geography_nuts_2024.csv',
            'data/reference/germany_plz_nuts_2024.csv',
            'data/reference/mpsv_kraje_nuts_2024.csv',
            'data/reference/mpsv_obce_kraj_2024.csv',
            'data/reference/mpsv_okresy_kraj_2024.csv',
            'data/reference/nav_region_nuts_2024.csv',
            'data/reference/vdab_postcode_nuts_2024.csv'
        ],
        union_by_name = true
    )
    where nuts_code is not null
        and nuts_label is not null
    group by nuts_code
    having count(distinct nuts_label) > 1
) as conflict
