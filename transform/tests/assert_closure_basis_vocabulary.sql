-- A posting leaving the source is only ever a source-reported or inferred removal. No other
-- basis (in particular anything implying time-to-hire) may enter the lifecycle vocabulary.

select source, scope_id, source_id, closure_basis
from {{ ref('posting_lifecycle') }}
where closure_basis is not null
    and closure_basis not in ('source_reported', 'inferred_absence')
