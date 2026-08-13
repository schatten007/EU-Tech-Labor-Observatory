{{
  config(
    materialized = 'view',
  )
}}

-- Source-agnostic posting contract. One row per (source, source_id, observed_at):
-- what we OBSERVED, never what we concluded. Closure is derived downstream from
-- absence across observations, and calibrated against removed_at where the source
-- supplies one (Sweden does; nothing else does).

select
    'jobtech'                                       as source,
    id                                              as source_id,

    -- JobTech `timestamp` is epoch millis, and is the ad's own version stamp rather
    -- than our observation time. Phase 1 replaces this with the partition's
    -- observed_at once the collector writes real raw partitions.
    cast(to_timestamp(timestamp / 1000) as timestamp) as observed_at,

    publication_date                                as first_published,
    last_publication_date                           as last_modified,
    try_cast(removed_date as timestamp)             as removed_at,

    -- Sweden publishes its own municipality/region codes, not NUTS. Deriving NUTS
    -- is a mapping step, not a rename: left null until the crosswalk lands.
    cast(null as varchar)                           as nuts_code,
    coalesce(country_code, 'SE')                    as country,

    -- Likewise: JobTech uses its own taxonomy concept ids, not ESCO URIs.
    cast(null as varchar)                           as esco_occupation_uri,
    'sv'                                            as lang

from {{ source('sample', 'postings_sample') }}
