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
    cast(source as varchar)                         as source,
    cast(source_id as varchar)                      as source_id,
    cast(observed_at as timestamp)                  as observed_at,
    try_cast(first_published as timestamp)          as first_published,
    try_cast(last_modified as timestamp)            as last_modified,
    try_cast(removed_at as timestamp)               as removed_at,
    cast(nuts_code as varchar)                      as nuts_code,
    cast(country as varchar)                        as country,
    cast(esco_occupation_uri as varchar)             as esco_occupation_uri,
    cast(lang as varchar)                           as lang

from {{ source('observations', 'postings') }}
