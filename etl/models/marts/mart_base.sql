-- Bang mart tong hop grain min nhat cua Southwest Airlines (WN) 2015-2018
{{ config(materialized='table') }}

SELECT
    year_month,
    day_of_week,
    time_block,
    origin,
    destination,
    distance_group,
    season,
    
    SUM(is_eligible)::INTEGER AS eligible_flights,
    SUM(is_delayed)::INTEGER AS delayed_flights,
    ROUND(SUM(CASE WHEN is_eligible = 1 THEN arr_delay ELSE 0 END), 2)::REAL AS arrival_delay_sum,
    SUM(CASE WHEN is_eligible = 1 THEN 1 ELSE 0 END)::INTEGER AS arrival_delay_count

FROM {{ ref('stg_flights') }}
WHERE carrier = 'WN'
GROUP BY
    year_month,
    day_of_week,
    time_block,
    origin,
    destination,
    distance_group,
    season
