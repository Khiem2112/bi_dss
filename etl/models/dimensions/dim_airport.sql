-- Bang chieu san bay noi dia My
{{ config(materialized='table') }}

WITH origins AS (
    SELECT DISTINCT origin AS airport_code
    FROM {{ ref('stg_flights') }}
),
destinations AS (
    SELECT DISTINCT destination AS airport_code
    FROM {{ ref('stg_flights') }}
),
all_airports AS (
    SELECT airport_code FROM origins
    UNION
    SELECT airport_code FROM destinations
)

SELECT
    airport_code,
    airport_code AS airport_name
FROM all_airports
WHERE airport_code IS NOT NULL AND airport_code != ''
ORDER BY airport_code
