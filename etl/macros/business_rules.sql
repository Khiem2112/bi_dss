{% macro time_block_expr(dep_time_col) %}
    CASE
        WHEN {{ dep_time_col }} < 600 THEN 'Early Morning'
        WHEN {{ dep_time_col }} < 1200 THEN 'Morning'
        WHEN {{ dep_time_col }} < 1800 THEN 'Afternoon'
        ELSE 'Evening'
    END
{% endmacro %}

{% macro season_expr(month_col) %}
    CASE
        WHEN {{ month_col }} IN (1, 2, 3) THEN 'Winter'
        WHEN {{ month_col }} IN (4, 5, 6) THEN 'Spring'
        WHEN {{ month_col }} IN (7, 8, 9) THEN 'Summer'
        ELSE 'Autumn'
    END
{% endmacro %}

{% macro distance_group_expr(distance_col) %}
    CASE
        WHEN {{ distance_col }} < 250 THEN 'G01'
        WHEN {{ distance_col }} < 500 THEN 'G02'
        WHEN {{ distance_col }} < 750 THEN 'G03'
        WHEN {{ distance_col }} < 1000 THEN 'G04'
        WHEN {{ distance_col }} < 1250 THEN 'G05'
        WHEN {{ distance_col }} < 1500 THEN 'G06'
        WHEN {{ distance_col }} < 1750 THEN 'G07'
        WHEN {{ distance_col }} < 2000 THEN 'G08'
        WHEN {{ distance_col }} < 2250 THEN 'G09'
        WHEN {{ distance_col }} < 2500 THEN 'G10'
        ELSE 'G11'
    END
{% endmacro %}
