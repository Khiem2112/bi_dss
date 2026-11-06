-- Bang mart tong hop grain min nhat cua Southwest Airlines (WN) 2015-2018
-- Nguon: fact_flight (grain chuyen bay), khong tinh truc tiep tu staging nua.
-- Baseline mac dinh: ty le tre toan mang WN trong cung season + time_block
-- (ngu canh so sanh nay la gia dinh tam thoi, can chot lai sau khi profiling xong).
{{ config(materialized='table') }}

{% set sample_size_threshold = var('sample_size_threshold', 30) %}

WITH segment AS (
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
        ROUND(SUM(CASE WHEN is_eligible = 1 THEN arr_delay ELSE 0 END), 2)::REAL AS arrival_delay_sum

    FROM {{ ref('fact_flight') }}
    WHERE carrier = 'WN'
    GROUP BY
        year_month,
        day_of_week,
        time_block,
        origin,
        destination,
        distance_group,
        season
),

baseline AS (
    SELECT
        season,
        time_block,
        SUM(is_eligible)::INTEGER AS baseline_eligible_flights,
        SUM(is_delayed)::INTEGER AS baseline_delayed_flights
    FROM {{ ref('fact_flight') }}
    WHERE carrier = 'WN'
    GROUP BY season, time_block
)

SELECT
    segment.year_month,
    segment.day_of_week,
    segment.time_block,
    segment.origin,
    segment.destination,
    segment.distance_group,
    segment.season,

    segment.eligible_flights,
    segment.delayed_flights,
    segment.arrival_delay_sum,
    ROUND(segment.arrival_delay_sum / NULLIF(segment.eligible_flights, 0), 2)::REAL AS average_arrival_delay,

    segment.eligible_flights AS sample_size,
    CASE
        WHEN segment.eligible_flights >= {{ sample_size_threshold }} THEN 'Sufficient'
        ELSE 'Low Sample'
    END AS sample_size_flag,

    ROUND(segment.delayed_flights * 100.0 / NULLIF(segment.eligible_flights, 0), 3)::REAL AS delay_rate,
    ROUND(baseline.baseline_delayed_flights * 100.0 / NULLIF(baseline.baseline_eligible_flights, 0), 3)::REAL AS baseline_delay_rate,
    ROUND(
        (segment.delayed_flights * 100.0 / NULLIF(segment.eligible_flights, 0))
        - (baseline.baseline_delayed_flights * 100.0 / NULLIF(baseline.baseline_eligible_flights, 0))
    , 3)::REAL AS baseline_gap

FROM segment
LEFT JOIN baseline
    ON segment.season = baseline.season
   AND segment.time_block = baseline.time_block
