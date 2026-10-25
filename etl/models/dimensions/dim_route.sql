-- Bang chieu tuyen bay co huong (origin -> destination)
{{ config(materialized='table') }}

SELECT DISTINCT
    origin,
    destination,
    origin || ' → ' || destination AS route_label,
    distance_group
FROM {{ ref('stg_flights') }}
WHERE origin IS NOT NULL AND destination IS NOT NULL
ORDER BY origin, destination
