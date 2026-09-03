{{
  config(
    materialized = 'view',
  )
}}

-- One row per nuts_code with its reference label, backfilling posting rows whose collector
-- resolved a code but no label (the ba segment paths built RegionResolution without nuts_label).
-- A stored partition is never rewritten, so the backfill happens here in staging, not at source.
-- The group by (not select distinct) makes one-row-per-code a structural invariant: a code
-- carrying two label spellings across files must collapse to one row or posting counts fan out.
-- Paths are enumerated, not globbed: a *_nuts_2024.csv glob would silently miss the two Slovak
-- mpsv files. union_by_name is required because germany_plz_nuts_2024.csv carries two extra
-- columns. dbt resolves relative paths from the repo root, matching stg_postings.
select
    cast(labels.nuts_code as varchar) as nuts_code,
    cast(min(labels.nuts_label) as varchar) as nuts_label
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
) as labels
where labels.nuts_code is not null
    and labels.nuts_label is not null
group by labels.nuts_code
