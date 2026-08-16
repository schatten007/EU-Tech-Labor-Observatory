-- Posting counts and advertised vacancy counts are distinct measures. At least one
-- published survival cell must report more advertised vacancies than postings, proving the
-- two are not conflated.

select 'no vacancy/posting divergence is published' as failure
where not exists (
    select 1
    from {{ ref('posting_survival') }}
    where posting_count is not null
        and advertised_vacancies is not null
        and advertised_vacancies > posting_count
)
