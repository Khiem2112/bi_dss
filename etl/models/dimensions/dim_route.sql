-- Bang chieu tuyen bay co huong (origin -> destination)
{{ config(materialized='table') }}

WITH routes AS (
    SELECT DISTINCT
        origin,
        destination,
        origin || ' → ' || destination AS route_label,
        distance_group
    FROM {{ ref('stg_flights') }}
    WHERE origin IS NOT NULL AND destination IS NOT NULL
)

SELECT
    ROW_NUMBER() OVER (ORDER BY origin, destination) AS route_key,
    origin,
    destination,
    route_label,
    distance_group
FROM routes

UNION ALL

SELECT
    -1 AS route_key,
    'UNKNOWN' AS origin,
    'UNKNOWN' AS destination,
    'Unknown Route' AS route_label,
    NULL AS distance_group

ORDER BY route_key
