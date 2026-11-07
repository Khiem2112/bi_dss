-- Bang mart so sanh Southwest (WN) voi hang tham chieu (DL, AA) trong cung
-- tuyen bay va boi canh thoi gian (route + time_block + year_month), phuc vu BQ-04/M-06.
-- Chi so sanh khi ca hai hang co du lieu trong cung segment; khong tu suy dien khi thieu.
{{ config(materialized='table') }}

{% set sample_size_threshold = var('sample_size_threshold', 30) %}
{% set benchmark_carriers = ['WN', 'DL', 'AA'] %}

WITH segment AS (
    SELECT
        year_month,
        time_block,
        origin,
        destination,
        carrier,

        SUM(is_eligible)::INTEGER AS eligible_flights,
        SUM(is_delayed)::INTEGER AS delayed_flights,
        ROUND(SUM(CASE WHEN is_eligible = 1 THEN arr_delay ELSE 0 END), 2)::REAL AS arrival_delay_sum

    FROM {{ ref('fact_flight') }}
    WHERE carrier IN ({{ "'" ~ benchmark_carriers | join("', '") ~ "'" }})
    GROUP BY year_month, time_block, origin, destination, carrier
),

comparable_routes AS (
    -- chi giu nhung to hop route+time+thang co du lieu cua CA WN lan it nhat
    -- mot hang tham chieu, de dam bao dieu kien so sanh hop le
    SELECT year_month, time_block, origin, destination
    FROM segment
    GROUP BY year_month, time_block, origin, destination
    HAVING COUNT(DISTINCT carrier) >= 2
       AND SUM(CASE WHEN carrier = 'WN' THEN 1 ELSE 0 END) > 0
),

-- Baseline cho BQ-04: ty le tre gop cua (cac) hang tham chieu (khac WN)
-- trong cung route + time_block + thang, chi tinh tren segment da du dieu kien so sanh.
reference_baseline AS (
    SELECT
        segment.year_month,
        segment.time_block,
        segment.origin,
        segment.destination,
        SUM(segment.eligible_flights)::INTEGER AS baseline_eligible_flights,
        SUM(segment.delayed_flights)::INTEGER AS baseline_delayed_flights
    FROM segment
    INNER JOIN comparable_routes
        ON segment.year_month = comparable_routes.year_month
       AND segment.time_block = comparable_routes.time_block
       AND segment.origin = comparable_routes.origin
       AND segment.destination = comparable_routes.destination
    WHERE segment.carrier != 'WN'
    GROUP BY segment.year_month, segment.time_block, segment.origin, segment.destination
)

SELECT
    segment.year_month,
    segment.time_block,
    segment.origin,
    segment.destination,
    segment.carrier,
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

    -- Baseline Delay Rate / Baseline Gap chi co y nghia cho dong WN (doi tuong duoc danh gia);
    -- dong cua chinh hang tham chieu de NULL vi khong tu so sanh voi chinh no.
    CASE WHEN segment.carrier = 'WN' THEN
        ROUND(reference_baseline.baseline_delayed_flights * 100.0 / NULLIF(reference_baseline.baseline_eligible_flights, 0), 3)::REAL
    END AS baseline_delay_rate,
    CASE WHEN segment.carrier = 'WN' THEN
        ROUND(
            (segment.delayed_flights * 100.0 / NULLIF(segment.eligible_flights, 0))
            - (reference_baseline.baseline_delayed_flights * 100.0 / NULLIF(reference_baseline.baseline_eligible_flights, 0))
        , 3)::REAL
    END AS baseline_gap

FROM segment
INNER JOIN comparable_routes
    ON segment.year_month = comparable_routes.year_month
   AND segment.time_block = comparable_routes.time_block
   AND segment.origin = comparable_routes.origin
   AND segment.destination = comparable_routes.destination
LEFT JOIN reference_baseline
    ON segment.year_month = reference_baseline.year_month
   AND segment.time_block = reference_baseline.time_block
   AND segment.origin = reference_baseline.origin
   AND segment.destination = reference_baseline.destination
