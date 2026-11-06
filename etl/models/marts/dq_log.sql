-- Data Quality Log: doi soat so dong va cac truong hop can luu y theo SC1/SC3.
-- Khong thay the verify_motherduck.py, chi dua ket qua doi soat vao luong dbt
-- de co the kiem tra bang dbt test thay vi chi chay script roi.
{{ config(materialized='table') }}

SELECT
    COUNT(*)::INTEGER AS total_records,
    SUM(CASE WHEN cancelled = 1 THEN 1 ELSE 0 END)::INTEGER AS cancelled_records,
    SUM(CASE WHEN diverted = 1 THEN 1 ELSE 0 END)::INTEGER AS diverted_records,
    SUM(CASE WHEN cancelled = 0 AND diverted = 0 AND arr_delay IS NULL THEN 1 ELSE 0 END)::INTEGER
        AS undetermined_outcome_records,
    SUM(is_eligible)::INTEGER AS eligible_records,
    SUM(is_delayed)::INTEGER AS delayed_records,
    SUM(CASE WHEN business_key_duplicate_flag THEN 1 ELSE 0 END)::INTEGER AS duplicate_business_key_records,
    SUM(CASE WHEN carrier_key = -1 THEN 1 ELSE 0 END)::INTEGER AS unmapped_carrier_records,
    SUM(CASE WHEN origin_airport_key = -1 OR destination_airport_key = -1 THEN 1 ELSE 0 END)::INTEGER
        AS unmapped_airport_records,
    SUM(CASE WHEN route_key = -1 THEN 1 ELSE 0 END)::INTEGER AS unmapped_route_records,
    SUM(CASE WHEN distance_group_key = -1 THEN 1 ELSE 0 END)::INTEGER AS unmapped_distance_group_records
FROM {{ ref('fact_flight') }}
