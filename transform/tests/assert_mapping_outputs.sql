with failures as (
    select 1 as failure
    from {{ ref('dimension_demand_latest') }}
    where value_uri is null or taxonomy_version not in ('NUTS-2024', '1.2.1')

    union all

    select 1
    from {{ ref('skill_demand_latest') }}
    where value_uri is null or taxonomy_version != '1.2.1'

    union all

    select 1
    from {{ ref('mapping_quality_latest') }}
    where mapping_status not in ('mapped', 'ambiguous', 'low_confidence', 'unmapped', 'not_present')
        or outcome_count < 1
        or total_outcomes < outcome_count
)

select * from failures
