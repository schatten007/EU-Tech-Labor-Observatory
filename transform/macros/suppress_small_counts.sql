-- Small-count disclosure control for published historical aggregates.
--
-- Cells describing a very small number of postings can single out an individual
-- employer or vacancy once combined with a narrow dimension (scope, period, closure
-- basis). We mask any non-zero group below this threshold. Zero stays visible: an
-- absence of postings is not disclosive, and hiding it would distort trends.
--
-- ponytail: one threshold, defined once, reused by every mart and its data test.

{% macro small_count_threshold() %}5{% endmacro %}

{% macro is_suppressed(count_expr) %}
    ({{ count_expr }} > 0 and {{ count_expr }} < {{ small_count_threshold() }})
{% endmacro %}

{% macro mask_small(value_expr, count_expr) %}
    case when {{ is_suppressed(count_expr) }} then null else {{ value_expr }} end
{% endmacro %}
