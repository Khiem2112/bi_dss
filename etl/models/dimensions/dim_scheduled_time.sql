-- Bang chieu thoi gian khoi hanh du kien (DimScheduledTime)
{{ config(materialized='table') }}

WITH distinct_times AS (
    SELECT DISTINCT crs_dep_time
    FROM {{ ref('stg_flights') }}
    WHERE crs_dep_time IS NOT NULL AND crs_dep_time >= 0 AND crs_dep_time <= 2400
)

SELECT
    crs_dep_time AS scheduled_time_key,
    crs_dep_time,
    LPAD((crs_dep_time // 100)::VARCHAR, 2, '0') || ':' || LPAD((crs_dep_time % 100)::VARCHAR, 2, '0') AS scheduled_departure_time,
    (crs_dep_time // 100)::INTEGER AS departure_hour,
    (crs_dep_time % 100)::INTEGER AS departure_minute,
    {{ time_block_expr('crs_dep_time') }} AS time_block,
    CASE
        WHEN crs_dep_time < 600 THEN 'Sáng sớm'
        WHEN crs_dep_time < 1200 THEN 'Buổi sáng'
        WHEN crs_dep_time < 1800 THEN 'Buổi chiều'
        ELSE 'Buổi tối'
    END AS time_block_vi
FROM distinct_times

UNION ALL

SELECT -1, NULL, 'Unknown', NULL, NULL, 'Unknown', 'Không xác định'

ORDER BY scheduled_time_key
