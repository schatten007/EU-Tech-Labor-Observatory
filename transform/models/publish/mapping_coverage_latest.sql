{{
  config(
    materialized = 'view',
  )
}}

-- The denominator that belongs beside every ranking. mapping_quality_latest cannot serve as one:
-- its skill rows come from stg_skill_mappings, so they count mappings rather than postings, and a
-- posting asking for five mapped skills would inflate the total it is measured against. Every
-- count here is a distinct posting, so the three columns read as one narrowing sequence: postings
-- observed, postings where the source supplied a structured value, postings with a usable mapped
-- value. Without it a ranked list of 18 occupations can be read as covering all 615 postings.

with latest as (
    select * from {{ ref('latest_complete_sweeps') }}
),
postings as (
    select
        postings.source,
        postings.scope_id,
        postings.sweep_id,
        postings.source_id,
        postings.region_mapping_status,
        postings.occupation_mapping_status,
        postings.nuts_version,
        postings.esco_version
    from {{ ref('stg_postings') }} as postings
    inner join latest
        on latest.source = postings.source and latest.scope_id = postings.scope_id
        and latest.sweep_id = postings.sweep_id
),
-- Collapse the per-skill grain to one flag pair per posting before counting: a posting counts once
-- however many skills it lists, and a posting with no structured skill still carries its single
-- not_present row.
posting_skills as (
    select
        source,
        scope_id,
        sweep_id,
        source_id,
        max(case when mapping_status <> 'not_present' then 1 else 0 end) as has_source_value,
        max(case when mapping_status = 'mapped' then 1 else 0 end) as has_mapped
    from {{ ref('stg_skill_mappings') }}
    group by all
),
region as (
    select
        source,
        scope_id,
        sweep_id,
        'region'::varchar as dimension,
        count(distinct source_id)::bigint as postings_total,
        count(distinct case when region_mapping_status <> 'not_present' then source_id end)::bigint
            as postings_with_source_value,
        count(distinct case when region_mapping_status = 'mapped' then source_id end)::bigint
            as postings_mapped,
        -- Aggregated, not grouped: the pinned reference version is constant within a sweep, and
        -- grouping by it would split the one-row-per-dimension grain if it ever drifted.
        max(nuts_version) as taxonomy_version
    from postings
    group by all
), occupation as (
    select
        source,
        scope_id,
        sweep_id,
        'occupation'::varchar as dimension,
        count(distinct source_id)::bigint as postings_total,
        count(distinct case
            when occupation_mapping_status <> 'not_present' then source_id
        end)::bigint as postings_with_source_value,
        count(distinct case when occupation_mapping_status = 'mapped' then source_id end)::bigint
            as postings_mapped,
        max(esco_version) as taxonomy_version
    from postings
    group by all
), skill as (
    -- Counted from postings outward rather than from the skill rows inward, so postings_total is
    -- the same 615 in all three rows and the narrowing sequence still holds for a posting whose
    -- skill array is empty rather than not_present.
    select
        postings.source,
        postings.scope_id,
        postings.sweep_id,
        'skill'::varchar as dimension,
        count(distinct postings.source_id)::bigint as postings_total,
        count(distinct case
            when posting_skills.has_source_value = 1 then postings.source_id
        end)::bigint as postings_with_source_value,
        count(distinct case
            when posting_skills.has_mapped = 1 then postings.source_id
        end)::bigint as postings_mapped,
        max(postings.esco_version) as taxonomy_version
    from postings
    left join posting_skills
        on posting_skills.source = postings.source
        and posting_skills.scope_id = postings.scope_id
        and posting_skills.sweep_id = postings.sweep_id
        and posting_skills.source_id = postings.source_id
    group by all
)
select * from region
union all
select * from occupation
union all
select * from skill
