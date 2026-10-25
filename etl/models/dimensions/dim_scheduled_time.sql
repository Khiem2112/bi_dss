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
    CASE
        WHEN crs_dep_time < 600 THEN 'Early Morning'
        WHEN crs_dep_time < 1200 THEN 'Morning'
        WHEN crs_dep_time < 1800 THEN 'Afternoon'
        ELSE 'Evening'
    END AS departure_time_block,
    CASE
        WHEN crs_dep_time < 600 THEN 'Early Morning'
        WHEN crs_dep_time < 1200 THEN 'Morning'
        WHEN crs_dep_time < 1800 THEN 'Afternoon'
        ELSE 'Evening'
    END AS time_block,
    CASE
        WHEN crs_dep_time < 600 THEN 'Sáng sớm'
        WHEN crs_dep_time < 1200 THEN 'Buổi sáng'
        WHEN crs_dep_time < 1800 THEN 'Buổi chiều'
        ELSE 'Buổi tối'
    END AS time_block_vi
FROM distinct_times
ORDER BY crs_dep_time
